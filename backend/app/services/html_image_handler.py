"""HTML 图片处理工具（扫描、下载、替换）。

概念：处理 HTML 文档中的图片标签，将外链/base64 图片替换为平台 URL
模块：services/html_image_handler.py
作用：
    - 扫描 HTML 中的 <img> 标签
    - 下载/解码图片
    - 上传到目标平台
    - 替换 src 属性
怎么写：
    - 使用正则表达式或 HTML 解析器
    - 异步处理多张图片
    - 错误处理（部分图片失败不影响整体）
"""

import logging
import re
from typing import Callable, Optional

from app.services.image_processor import ImageProcessor, ImageProcessorError

logger = logging.getLogger(__name__)


class HtmlImageHandler:
    """HTML 图片处理器。

    使用方法：
        handler = HtmlImageHandler()

        async def upload_func(image_data: bytes, filename: str) -> str:
            # 上传到微信/知乎/其他平台
            return "https://platform.com/uploaded/image.jpg"

        new_html = await handler.process_images(html, upload_func)
    """

    def __init__(self, image_processor: Optional[ImageProcessor] = None):
        """初始化 HTML 图片处理器。

        Args:
            image_processor: 图片处理器实例（默认创建新实例）
        """
        self.processor = image_processor or ImageProcessor()

    async def process_images(
        self,
        html: str,
        upload_callback: Callable[[bytes, str], str],
        on_error: str = "keep",
    ) -> tuple[str, list[dict]]:
        """处理 HTML 中的所有图片。

        Args:
            html: HTML 内容
            upload_callback: 上传回调函数 (image_data, filename) -> platform_url
                注意：这个回调必须是同步函数或返回字符串的协程
            on_error: 错误处理策略
                - "keep": 保留原始 src（默认）
                - "remove": 移除整个 <img> 标签
                - "placeholder": 替换为占位图

        Returns:
            (新 HTML, 处理结果列表)
            处理结果格式: [{"src": "...", "new_src": "...", "status": "success/failed", "error": "..."}]

        Raises:
            不会抛出异常，错误会记录在返回的结果列表中
        """
        # 查找所有 <img> 标签
        img_pattern = re.compile(
            r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*>',
            re.IGNORECASE | re.DOTALL
        )

        results = []
        new_html = html

        for match in img_pattern.finditer(html):
            img_tag = match.group(0)
            src = match.group(1)

            # 跳过已经是微信 URL 的图片（mmbiz.qpic.cn）
            if "mmbiz.qpic.cn" in src or "qlogo.cn" in src:
                logger.debug(f"Skipping WeChat image: {src[:100]}")
                continue

            # 处理单张图片
            result = await self._process_single_image(src, upload_callback)
            results.append(result)

            # 根据处理结果替换 HTML
            if result["status"] == "success" and result["new_src"]:
                # 替换 src 属性
                new_img_tag = img_tag.replace(src, result["new_src"])
                new_html = new_html.replace(img_tag, new_img_tag, 1)
            elif result["status"] == "failed":
                # 错误处理
                if on_error == "remove":
                    new_html = new_html.replace(img_tag, "", 1)
                elif on_error == "placeholder":
                    placeholder = '<p style="color: #999;">[图片加载失败]</p>'
                    new_html = new_html.replace(img_tag, placeholder, 1)
                # "keep" 策略不修改

        logger.info(f"Processed {len(results)} images, {sum(1 for r in results if r['status'] == 'success')} succeeded")
        return new_html, results

    async def _process_single_image(
        self,
        src: str,
        upload_callback: Callable[[bytes, str], str],
    ) -> dict:
        """处理单张图片。

        Args:
            src: 图片 src 属性（URL 或 base64）
            upload_callback: 上传回调函数

        Returns:
            处理结果字典
        """
        result = {
            "src": src[:200],  # 截断过长的 base64
            "new_src": None,
            "status": "pending",
            "error": None,
        }

        try:
            # 1. 获取图片数据
            if self.processor.is_base64_image(src):
                logger.debug("Processing base64 image")
                image_data = self.processor.decode_base64_image(src)
                filename = "base64_image.jpg"
            elif self.processor.is_external_url(src):
                logger.debug(f"Downloading image from {src[:100]}")
                image_data = await self.processor.download_image(src)
                filename = self.processor.extract_filename_from_url(src)
            else:
                # 相对路径或其他格式，跳过
                result["status"] = "skipped"
                result["error"] = "Unsupported src format (relative path or invalid)"
                return result

            # 2. 验证图片
            format_name, width, height = self.processor.validate_image(image_data)
            logger.debug(f"Image validated: {format_name}, {width}x{height}")

            # 3. 优化图片（针对微信）
            optimized_data = self.processor.optimize_for_wechat(image_data)

            # 4. 上传到平台
            platform_url = await upload_callback(optimized_data, filename)

            result["new_src"] = platform_url
            result["status"] = "success"
            logger.info(f"Image processed successfully: {src[:50]} -> {platform_url[:50]}")

        except ImageProcessorError as e:
            result["status"] = "failed"
            result["error"] = e.message
            logger.warning(f"Failed to process image {src[:100]}: {e.message}")

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(f"Unexpected error processing image {src[:100]}: {e}", exc_info=True)

        return result

    def count_images(self, html: str) -> int:
        """统计 HTML 中的图片数量。

        Args:
            html: HTML 内容

        Returns:
            图片数量
        """
        img_pattern = re.compile(r'<img\s+[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)
        return len(img_pattern.findall(html))

    def extract_image_srcs(self, html: str) -> list[str]:
        """提取 HTML 中所有图片的 src。

        Args:
            html: HTML 内容

        Returns:
            src 列表
        """
        img_pattern = re.compile(r'<img\s+[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)
        return img_pattern.findall(html)
