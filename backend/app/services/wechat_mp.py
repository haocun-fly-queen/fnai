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
import os
import re
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wechat_token import WechatTokenError, WechatTokenManager

# 默认封面图路径（微信草稿接口必填 thumb_media_id）
_DEFAULT_COVER_PATH = Path(__file__).parent.parent / "static" / "default_cover.jpg"

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
    MASS_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/mass/sendall"
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
        config_thumb_media_id: Optional[str] = None,
        need_open_comment: bool = True,
        only_fans_can_comment: bool = False,
    ) -> dict[str, Any]:
        """发布文章到微信公众号。

        Args:
            title: 文章标题（必填，不超过 64 字）
            content: 文章正文，HTML 格式（必填）
            author: 作者名称（可选）
            digest: 摘要（可选，最多 120 字）
            thumb_media_id: 封面图素材 ID（请求中指定，优先级最高）
            config_thumb_media_id: 配置中的默认封面图素材 ID（备选）
            need_open_comment: 是否打开评论
            only_fans_can_comment: 是否仅粉丝可评论

        Returns:
            {
                "publish_id": "发布任务 ID",
                "draft_media_id": "草稿素材 ID",
                "thumb_media_id": "使用的封面图素材 ID"
            }

        Raises:
            WechatMpError: 发布失败
        """
        # 1. 参数验证
        self._validate_params(title, content)

        # 2. 确定封面图 media_id（微信草稿接口必填）
        #    优先级：请求参数 > 配置默认 > 自动上传内置封面
        effective_thumb = thumb_media_id or config_thumb_media_id
        if not effective_thumb:
            effective_thumb = await self.get_or_upload_default_thumb()

        # 3. 获取 access_token（带重试）
        token = await self._get_token_with_retry()

        # 4. 创建草稿（带重试）
        draft_media_id = await self._create_draft_with_retry(
            token=token,
            title=title,
            content=content,
            author=author,
            digest=digest,
            thumb_media_id=effective_thumb,
            need_open_comment=need_open_comment,
            only_fans_can_comment=only_fans_can_comment,
        )

        # 5. 发布草稿（带重试）
        publish_id = await self._submit_publish_with_retry(token, draft_media_id)

        return {
            "publish_id": publish_id,
            "draft_media_id": draft_media_id,
            "thumb_media_id": effective_thumb,
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

    async def send_mass_message(
        self,
        media_id: str,
        send_ignore_reprint: bool = False,
    ) -> dict[str, Any]:
        """群发图文消息给所有粉丝。

        注意：
        1. 使用 draft_media_id（草稿素材ID，从 publish_article 返回）
        2. 群发给所有粉丝（认证号可用标签筛选）
        3. 测试号每天只能群发1次，认证号每月4次
        4. 群发后粉丝会收到推送消息
        5. 微信群发使用的是草稿的 media_id，不是已发布文章的 article_id

        Args:
            media_id: 草稿素材 ID（draft_media_id，从 publish_article 返回）
            send_ignore_reprint: 是否转载（true=原创，false=转载）

        Returns:
            {
                "msg_id": "群发消息ID",
                "msg_data_id": "消息数据ID"
            }

        Raises:
            WechatMpError: 群发失败
        """
        token = await self._get_token_with_retry()

        # 构建群发请求体
        # filter: {"is_to_all": true} 表示发给所有粉丝
        # mpnews: 图文消息类型
        payload = {
            "filter": {
                "is_to_all": True
            },
            "mpnews": {
                "media_id": media_id
            },
            "msgtype": "mpnews",
            "send_ignore_reprint": 1 if send_ignore_reprint else 0
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.MASS_SEND_URL}?access_token={token}",
                    json=payload,
                )
                data = response.json()
            except httpx.TimeoutException:
                raise WechatMpError(
                    code="timeout",
                    message="群发消息超时",
                    retryable=True,
                )
            except httpx.NetworkError as e:
                raise WechatMpError(
                    code="network_error",
                    message=f"网络错误: {e}",
                    retryable=True,
                )

            if "errcode" in data and data["errcode"] != 0:
                # 常见错误码
                error_messages = {
                    45008: "图文消息超过限制（单次最多8条）",
                    45009: "接口调用超过限制（测试号每天1次，认证号每月4次）",
                    45015: "回复时间超过限制",
                    45047: "客服接口下行条数超过上限",
                    48001: "API功能未授权（需要认证或开通权限）",
                    48002: "粉丝拒收（用户设置拒收该公众号消息）",
                }

                errcode = data.get("errcode")
                errmsg = error_messages.get(errcode, data.get("errmsg", "未知错误"))

                raise WechatMpError(
                    code="mass_send_failed",
                    message=f"群发失败: {errmsg}",
                    wx_errcode=errcode,
                    retryable=(errcode in self.RETRYABLE_WX_CODES),
                )

            logger.info(f"Mass message sent: msg_id={data.get('msg_id')}")
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

    async def upload_thumb_image(self, image_data: bytes, filename: str = "cover.jpg") -> str:
        """上传永久素材图片，获取 thumb_media_id。

        微信草稿接口的 thumb_media_id 必须是永久素材的 media_id。
        使用 /cgi-bin/material/add_material?type=thumb 上传。

        Args:
            image_data: 图片二进制数据（JPEG，建议 900x383，< 64KB）
            filename: 文件名

        Returns:
            media_id（永久素材 ID，用于 thumb_media_id）

        Raises:
            WechatMpError: 上传失败
        """
        token = await self._get_token_with_retry()

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                files = {"media": (filename, image_data, "image/jpeg")}
                response = await client.post(
                    f"{self.UPLOAD_MATERIAL_URL}?access_token={token}&type=thumb",
                    files=files,
                )
                data = response.json()
            except httpx.TimeoutException:
                raise WechatMpError(
                    code="timeout",
                    message="上传封面图超时",
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
                    message=f"上传封面图失败: {data.get('errmsg', '未知错误')}",
                    wx_errcode=data.get("errcode"),
                )

            media_id = data.get("media_id")
            if not media_id:
                raise WechatMpError(
                    code="upload_failed",
                    message=f"上传封面图返回数据异常: {data}",
                )

            logger.info(f"Thumb uploaded: media_id={media_id}")
            return media_id

    async def get_or_upload_default_thumb(self, config_thumb_media_id: Optional[str] = None) -> str:
        """获取默认封面图的 media_id。

        优先使用配置中已有的 thumb_media_id，
        否则上传内置默认封面图并返回新的 media_id。

        Args:
            config_thumb_media_id: 配置中已存储的 thumb_media_id（可选）

        Returns:
            有效的 thumb_media_id

        Raises:
            WechatMpError: 上传失败且无可用默认封面
        """
        # 如果配置中已有 thumb_media_id，直接使用
        if config_thumb_media_id:
            return config_thumb_media_id

        # 上传默认封面图
        if not _DEFAULT_COVER_PATH.exists():
            raise WechatMpError(
                code="no_thumb",
                message="未提供封面图且默认封面图不存在，请在配置中上传封面图",
            )

        logger.info("Uploading default cover image as thumb material")
        image_data = _DEFAULT_COVER_PATH.read_bytes()
        return await self.upload_thumb_image(image_data, "default_cover.jpg")

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

            # 微信返回的 publish_id 可能是整数，统一转为字符串
            publish_id = str(data["publish_id"])
            logger.info(f"Publish submitted: publish_id={publish_id}")
            return publish_id

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
