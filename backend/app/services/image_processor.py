"""图片处理服务（图片下载、转换、上传）。

概念：处理文章中的图片，使其符合发布平台的要求
模块：services/image_processor.py
作用：
    - 下载外链图片
    - 解码 base64 图片
    - 转换图片格式
    - 压缩图片大小
怎么写：
    - 支持多种图片格式（JPEG, PNG, GIF, WebP）
    - 限制文件大小（防止内存溢出）
    - 错误处理（下载失败、格式不支持等）
"""

import base64
import io
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


class ImageProcessorError(Exception):
    """图片处理失败。"""

    def __init__(self, message: str, image_url: Optional[str] = None):
        self.message = message
        self.image_url = image_url
        super().__init__(message)


class ImageProcessor:
    """图片处理器。

    使用方法：
        processor = ImageProcessor(max_size_mb=5)
        image_data = await processor.download_image("https://example.com/image.jpg")
        optimized = processor.optimize_for_wechat(image_data)
    """

    # 支持的图片格式
    SUPPORTED_FORMATS = {"JPEG", "PNG", "GIF", "WEBP", "BMP"}

    # 微信图片要求
    WECHAT_MAX_SIZE = 10 * 1024 * 1024  # 10MB
    WECHAT_RECOMMENDED_SIZE = 1024 * 1024  # 1MB（推荐）

    def __init__(self, max_size_mb: int = 10, timeout: int = 30):
        """初始化图片处理器。

        Args:
            max_size_mb: 最大下载文件大小（MB）
            timeout: 下载超时时间（秒）
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.timeout = timeout

    async def download_image(self, url: str) -> bytes:
        """下载外链图片。

        Args:
            url: 图片 URL

        Returns:
            图片二进制数据

        Raises:
            ImageProcessorError: 下载失败或文件过大
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                # 检查 Content-Type
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    raise ImageProcessorError(
                        f"URL 不是图片类型: {content_type}",
                        url,
                    )

                # 检查文件大小
                content = response.content
                if len(content) > self.max_size_bytes:
                    raise ImageProcessorError(
                        f"图片文件过大: {len(content) / 1024 / 1024:.1f}MB，最大允许 {self.max_size_bytes / 1024 / 1024}MB",
                        url,
                    )

                logger.info(f"Downloaded image from {url}, size={len(content)} bytes")
                return content

        except httpx.HTTPStatusError as e:
            raise ImageProcessorError(
                f"下载图片失败: HTTP {e.response.status_code}",
                url,
            )
        except httpx.TimeoutException:
            raise ImageProcessorError(
                f"下载图片超时（{self.timeout}s）",
                url,
            )
        except httpx.RequestError as e:
            raise ImageProcessorError(
                f"下载图片失败: {e}",
                url,
            )

    def decode_base64_image(self, base64_data: str) -> bytes:
        """解码 base64 图片数据。

        Args:
            base64_data: base64 字符串（可能包含 data:image/png;base64, 前缀）

        Returns:
            图片二进制数据

        Raises:
            ImageProcessorError: 解码失败
        """
        try:
            # 移除 data:image/...;base64, 前缀
            if "," in base64_data:
                base64_data = base64_data.split(",", 1)[1]

            # 解码
            image_data = base64.b64decode(base64_data)

            # 检查大小
            if len(image_data) > self.max_size_bytes:
                raise ImageProcessorError(
                    f"Base64 图片过大: {len(image_data) / 1024 / 1024:.1f}MB"
                )

            logger.debug(f"Decoded base64 image, size={len(image_data)} bytes")
            return image_data

        except Exception as e:
            raise ImageProcessorError(f"Base64 解码失败: {e}")

    def validate_image(self, image_data: bytes) -> tuple[str, int, int]:
        """验证图片数据是否有效。

        Args:
            image_data: 图片二进制数据

        Returns:
            (format, width, height) 元组

        Raises:
            ImageProcessorError: 图片无效或格式不支持
        """
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                format_name = img.format
                if format_name not in self.SUPPORTED_FORMATS:
                    raise ImageProcessorError(
                        f"不支持的图片格式: {format_name}，支持的格式: {self.SUPPORTED_FORMATS}"
                    )

                width, height = img.size
                logger.debug(f"Image validated: {format_name}, {width}x{height}")
                return format_name, width, height

        except Exception as e:
            raise ImageProcessorError(f"图片验证失败: {e}")

    def optimize_for_wechat(self, image_data: bytes) -> bytes:
        """优化图片以适配微信要求。

        微信要求：
            - 格式：JPG/PNG
            - 大小：< 10MB（推荐 < 1MB）
            - 封面图：建议 900x383

        Args:
            image_data: 原始图片数据

        Returns:
            优化后的图片数据（JPEG 格式）

        Raises:
            ImageProcessorError: 处理失败
        """
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                # 转换为 RGB（去除透明通道，JPEG 不支持）
                if img.mode in ("RGBA", "LA", "P"):
                    # 创建白色背景
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # 如果图片已经很小，直接返回
                if len(image_data) <= self.WECHAT_RECOMMENDED_SIZE:
                    output = io.BytesIO()
                    img.save(output, format="JPEG", quality=85, optimize=True)
                    return output.getvalue()

                # 压缩图片（逐步降低质量）
                for quality in [85, 75, 65, 55]:
                    output = io.BytesIO()
                    img.save(output, format="JPEG", quality=quality, optimize=True)
                    compressed = output.getvalue()

                    if len(compressed) <= self.WECHAT_RECOMMENDED_SIZE:
                        logger.info(
                            f"Image optimized: {len(image_data)} -> {len(compressed)} bytes (quality={quality})"
                        )
                        return compressed

                # 如果压缩后还是太大，缩小尺寸
                width, height = img.size
                scale = 0.8
                while len(compressed) > self.WECHAT_RECOMMENDED_SIZE and scale > 0.3:
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    output = io.BytesIO()
                    resized.save(output, format="JPEG", quality=75, optimize=True)
                    compressed = output.getvalue()

                    logger.info(
                        f"Image resized: {width}x{height} -> {new_width}x{new_height}, size={len(compressed)} bytes"
                    )

                    scale -= 0.1

                return compressed

        except Exception as e:
            raise ImageProcessorError(f"图片优化失败: {e}")

    def is_external_url(self, src: str) -> bool:
        """判断是否为外链 URL。

        Args:
            src: img 标签的 src 属性

        Returns:
            True 表示是外链 URL（需要下载）
        """
        if src.startswith("data:"):
            return False  # base64

        try:
            parsed = urlparse(src)
            return parsed.scheme in ("http", "https")
        except Exception:
            return False

    def is_base64_image(self, src: str) -> bool:
        """判断是否为 base64 图片。

        Args:
            src: img 标签的 src 属性

        Returns:
            True 表示是 base64 数据
        """
        return src.startswith("data:image/")

    def extract_filename_from_url(self, url: str) -> str:
        """从 URL 提取文件名。

        Args:
            url: 图片 URL

        Returns:
            文件名（默认 image.jpg）
        """
        try:
            parsed = urlparse(url)
            path = parsed.path
            if path:
                filename = path.split("/")[-1]
                if filename and "." in filename:
                    return filename
        except Exception:
            pass

        return "image.jpg"
