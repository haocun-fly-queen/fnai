"""微信公众号发布服务（阶段 5 — 微信公众号对接）。

概念：封装微信公众号 API，支持草稿创建和文章发布。
模块：services/wechat_mp.py
作用：发布文章到微信公众号
怎么写：
    - 微信发布流程：获取 token → 创建草稿 → 发布草稿
    - 支持重试机制（指数退避）
    - 支持降级策略（Webhook / 手动复制）
    - 完整的错误处理和日志记录

微信公众号 API 文档：
    - 草稿接口：https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html
    - 发布接口：https://developers.weixin.qq.com/doc/offiaccount/Publish/Publish.html
"""

import asyncio
import logging
import re
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wechat_token import WechatTokenError, WechatTokenManager

logger = logging.getLogger(__name__)


class WechatMpError(Exception):
    """微信公众号操作失败。"""

    def __init__(
        self,
        code: str,
        message: str,
        wx_errcode: Optional[int] = None,
        retryable: bool = False,
    ):
        self.code = code
        self.message = message
        self.wx_errcode = wx_errcode
        self.retryable = retryable
        super().__init__(message)


class WechatMpClient:
    """微信公众号客户端。

    使用方法：
        client = WechatMpClient(db, app_id, app_secret)
        result = await client.publish_article(
            title="文章标题",
            content="<p>HTML 内容</p>",
            author="作者",
            digest="摘要"
        )
    """

    # API 端点
    DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
    PUBLISH_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"
    PUBLISH_STATUS_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/get"
    UPLOAD_IMAGE_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"
    UPLOAD_MATERIAL_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"

    # 重试配置
    MAX_RETRIES = 3
    BASE_DELAY = 1.0

    # 可重试的微信错误码
    RETRYABLE_WX_CODES = {
        -1,      # 系统繁忙
        45009,   # 接口调用超过限制
        45011,   # 频率限制
        48001,   # 功能未授权
    }

    def __init__(self, db: AsyncSession, app_id: str, app_secret: str):
        self.db = db
        self.app_id = app_id
        self.app_secret = app_secret
        self.token_manager = WechatTokenManager(db)

    async def publish_article(
        self,
        title: str,
        content: str,
        author: str = "",
        digest: str = "",
        thumb_media_id: Optional[str] = None,
        need_open_comment: bool = True,
        only_fans_can_comment: bool = False,
    ) -> dict[str, Any]:
        """发布文章到微信公众号。

        Args:
            title: 文章标题（必填，不超过 64 字）
            content: 文章正文，HTML 格式（必填）
            author: 作者名称（可选）
            digest: 摘要（可选，最多 120 字）
            thumb_media_id: 封面图素材 ID（可选）
            need_open_comment: 是否打开评论
            only_fans_can_comment: 是否仅粉丝可评论

        Returns:
            {
                "publish_id": "发布任务 ID",
                "draft_media_id": "草稿素材 ID"
            }

        Raises:
            WechatMpError: 发布失败
        """
        # 1. 参数验证
        self._validate_params(title, content)

        # 2. 获取 access_token（带重试）
        token = await self._get_token_with_retry()

        # 3. 创建草稿（带重试）
        draft_media_id = await self._create_draft_with_retry(
            token=token,
            title=title,
            content=content,
            author=author,
            digest=digest,
            thumb_media_id=thumb_media_id,
            need_open_comment=need_open_comment,
            only_fans_can_comment=only_fans_can_comment,
        )

        # 4. 发布草稿（带重试）
        publish_id = await self._submit_publish_with_retry(token, draft_media_id)

        return {
            "publish_id": publish_id,
            "draft_media_id": draft_media_id,
        }

    async def get_publish_status(self, publish_id: str) -> dict[str, Any]:
        """查询发布状态。

        Args:
            publish_id: 发布任务 ID

        Returns:
            {
                "publish_id": "发布任务 ID",
                "publish_status": 0,  # 0=成功, 1=发布中, 2+=失败原因
                "article_id": "文章 ID",
                "article_url": "文章链接"  # 发布成功后有值
            }

        Raises:
            WechatMpError: 查询失败
        """
        token = await self._get_token_with_retry()

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.PUBLISH_STATUS_URL}?access_token={token}",
                    json={"publish_id": publish_id},
                )
                data = response.json()
            except httpx.TimeoutException:
                raise WechatMpError(
                    code="timeout",
                    message="查询发布状态超时",
                    retryable=True,
                )
            except httpx.NetworkError as e:
                raise WechatMpError(
                    code="network_error",
                    message=f"网络错误: {e}",
                    retryable=True,
                )

            if "errcode" in data and data["errcode"] != 0:
                raise WechatMpError(
                    code="status_query_failed",
                    message=f"查询状态失败: {data.get('errmsg', '未知错误')}",
                    wx_errcode=data.get("errcode"),
                )

            return data

    async def upload_image(self, image_data: bytes, filename: str) -> str:
        """上传图片素材，获取 URL。

        Args:
            image_data: 图片二进制数据
            filename: 文件名

        Returns:
            图片 URL（用于文章内引用）

        Raises:
            WechatMpError: 上传失败
        """
        token = await self._get_token_with_retry()

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                files = {"media": (filename, image_data, "image/jpeg")}
                response = await client.post(
                    f"{self.UPLOAD_IMAGE_URL}?access_token={token}",
                    files=files,
                )
                data = response.json()
            except httpx.TimeoutException:
                raise WechatMpError(
                    code="timeout",
                    message="上传图片超时",
                    retryable=True,
                )
            except httpx.NetworkError as e:
                raise WechatMpError(
                    code="network_error",
                    message=f"网络错误: {e}",
                    retryable=True,
                )

            if "errcode" in data and data["errcode"] != 0:
                raise WechatMpError(
                    code="upload_failed",
                    message=f"上传图片失败: {data.get('errmsg', '未知错误')}",
                    wx_errcode=data.get("errcode"),
                )

            return data["url"]

    # ============================================================
    # 内部方法：带重试的 API 调用
    # ============================================================

    async def _get_token_with_retry(self) -> str:
        """获取 token（带重试）。"""
        last_error = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await self.token_manager.get_token(
                    self.app_id, self.app_secret
                )
            except WechatTokenError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    delay = self.BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Get token failed, retrying in {delay}s: {e.message}"
                    )
                    await asyncio.sleep(delay)

        raise WechatMpError(
            code="token_failed",
            message=f"获取 token 失败: {last_error.message}",
        )

    async def _create_draft_with_retry(self, **kwargs) -> str:
        """创建草稿（带重试）。"""
        last_error = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await self._create_draft(**kwargs)
            except WechatMpError as e:
                last_error = e
                if not e.retryable or attempt >= self.MAX_RETRIES:
                    raise
                delay = self.BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Create draft failed, retrying in {delay}s: {e.message}"
                )
                await asyncio.sleep(delay)

        raise last_error

    async def _submit_publish_with_retry(self, token: str, media_id: str) -> str:
        """提交发布（带重试）。"""
        last_error = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await self._submit_publish(token, media_id)
            except WechatMpError as e:
                last_error = e
                if not e.retryable or attempt >= self.MAX_RETRIES:
                    raise
                delay = self.BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Submit publish failed, retrying in {delay}s: {e.message}"
                )
                await asyncio.sleep(delay)

        raise last_error

    # ============================================================
    # 内部方法：核心 API 调用
    # ============================================================

    async def _create_draft(
        self,
        token: str,
        title: str,
        content: str,
        author: str,
        digest: str,
        thumb_media_id: Optional[str],
        need_open_comment: bool,
        only_fans_can_comment: bool,
    ) -> str:
        """创建草稿。

        微信草稿接口：
            URL: https://api.weixin.qq.com/cgi-bin/draft/add
            方法: POST
            参数:
                - articles: 文章数组（目前只支持一篇）
                    - title: 标题
                    - content: 正文（HTML）
                    - author: 作者
                    - digest: 摘要
                    - thumb_media_id: 封面图素材 ID
                    - need_open_comment: 是否打开评论 (0/1)
                    - only_fans_can_comment: 是否仅粉丝可评论 (0/1)

        Returns:
            草稿的 media_id
        """
        # 构建文章数据
        article = {
            "title": title,
            "content": self._sanitize_html(content),
            "author": author or "FNAI",
            "digest": digest[:120] if digest else "",
            "need_open_comment": 1 if need_open_comment else 0,
            "only_fans_can_comment": 1 if only_fans_can_comment else 0,
        }

        # 如果有封面图，添加到文章
        if thumb_media_id:
            article["thumb_media_id"] = thumb_media_id

        payload = {"articles": [article]}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.DRAFT_ADD_URL}?access_token={token}",
                    json=payload,
                )
                data = response.json()
            except httpx.TimeoutException:
                raise WechatMpError(
                    code="timeout",
                    message="创建草稿超时",
                    retryable=True,
                )
            except httpx.NetworkError as e:
                raise WechatMpError(
                    code="network_error",
                    message=f"网络错误: {e}",
                    retryable=True,
                )

            # 检查错误
            if "errcode" in data and data["errcode"] != 0:
                error_code = data["errcode"]
                error_msg = data.get("errmsg", "未知错误")
                retryable = error_code in self.RETRYABLE_WX_CODES

                logger.error(
                    f"Create draft failed: errcode={error_code}, errmsg={error_msg}"
                )
                raise WechatMpError(
                    code="draft_failed",
                    message=f"创建草稿失败: {error_msg}",
                    wx_errcode=error_code,
                    retryable=retryable,
                )

            if "media_id" not in data:
                raise WechatMpError(
                    code="draft_failed",
                    message=f"创建草稿返回数据异常: {data}",
                )

            logger.info(f"Draft created: media_id={data['media_id']}")
            return data["media_id"]

    async def _submit_publish(self, token: str, media_id: str) -> str:
        """提交发布任务。

        微信发布接口：
            URL: https://api.weixin.qq.com/cgi-bin/freepublish/submit
            方法: POST
            参数:
                - media_id: 草稿素材 ID

        Returns:
            publish_id（发布任务 ID，用于查询状态）
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.PUBLISH_URL}?access_token={token}",
                    json={"media_id": media_id},
                )
                data = response.json()
            except httpx.TimeoutException:
                raise WechatMpError(
                    code="timeout",
                    message="提交发布超时",
                    retryable=True,
                )
            except httpx.NetworkError as e:
                raise WechatMpError(
                    code="network_error",
                    message=f"网络错误: {e}",
                    retryable=True,
                )

            # 检查错误
            if "errcode" in data and data["errcode"] != 0:
                error_code = data["errcode"]
                error_msg = data.get("errmsg", "未知错误")
                retryable = error_code in self.RETRYABLE_WX_CODES

                logger.error(
                    f"Submit publish failed: errcode={error_code}, errmsg={error_msg}"
                )
                raise WechatMpError(
                    code="publish_failed",
                    message=f"提交发布失败: {error_msg}",
                    wx_errcode=error_code,
                    retryable=retryable,
                )

            if "publish_id" not in data:
                raise WechatMpError(
                    code="publish_failed",
                    message=f"提交发布返回数据异常: {data}",
                )

            logger.info(f"Publish submitted: publish_id={data['publish_id']}")
            return data["publish_id"]

    # ============================================================
    # 内部方法：HTML 清理
    # ============================================================

    def _sanitize_html(self, html: str) -> str:
        """清理 HTML，适配微信公众号格式要求。

        微信公众号要求：
        1. 只支持特定 HTML 标签
        2. 不支持 script、iframe 等危险标签
        3. 图片必须用微信素材 URL（这里先做基本清理）
        """
        # 移除 script、iframe、style 标签
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        html = re.sub(r"<iframe[^>]*>.*?</iframe>", "", html, flags=re.DOTALL)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)

        # 移除事件属性（onclick、onerror 等）
        html = re.sub(r'\s+on\w+="[^"]*"', "", html)
        html = re.sub(r"\s+on\w+='[^']*'", "", html)

        # 移除危险的 href（javascript:）
        html = re.sub(r'href="javascript:[^"]*"', 'href="#"', html)

        return html

    def _validate_params(self, title: str, content: str) -> None:
        """验证发布参数。"""
        if not title or not title.strip():
            raise WechatMpError(
                code="invalid_params",
                message="文章标题不能为空",
            )

        if len(title) > 64:
            raise WechatMpError(
                code="invalid_params",
                message=f"文章标题不能超过 64 字，当前 {len(title)} 字",
            )

        if not content or not content.strip():
            raise WechatMpError(
                code="invalid_params",
                message="文章内容不能为空",
            )

        # 微信对正文长度有限制（约 20000 字符）
        if len(content) > 20000:
            logger.warning(
                f"Content too long ({len(content)} chars), may be truncated by WeChat"
            )
