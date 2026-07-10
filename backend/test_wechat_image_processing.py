"""测试微信图片处理功能。

使用方法：
    python test_wechat_image_processing.py
"""

import asyncio
import sys
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.services.html_image_handler import HtmlImageHandler
from app.services.image_processor import ImageProcessor


async def mock_upload(image_data: bytes, filename: str) -> str:
    """模拟上传到微信（测试用）。"""
    print(f"  [MOCK] Uploading {filename}, size={len(image_data)} bytes")
    return f"https://mmbiz.qpic.cn/mocked/{filename}"


async def test_external_image():
    """测试外链图片处理。"""
    print("\n=== Test 1: External Image ===")

    html = """
    <p>这是一篇测试文章</p>
    <img src="https://picsum.photos/800/600" alt="测试图片" />
    <p>更多内容</p>
    """

    handler = HtmlImageHandler()
    new_html, results = await handler.process_images(html, mock_upload)

    print(f"Original HTML length: {len(html)}")
    print(f"Processed HTML length: {len(new_html)}")
    print(f"Images processed: {len(results)}")

    for i, result in enumerate(results, 1):
        print(f"  Image {i}:")
        print(f"    Status: {result['status']}")
        print(f"    Original: {result['src'][:100]}")
        if result['new_src']:
            print(f"    New: {result['new_src'][:100]}")
        if result['error']:
            print(f"    Error: {result['error']}")


async def test_base64_image():
    """测试 base64 图片处理。"""
    print("\n=== Test 2: Base64 Image ===")

    # 一个 1x1 像素的红色 PNG (base64)
    base64_img = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    )

    html = f"""
    <p>Base64 图片测试</p>
    <img src="{base64_img}" alt="红点" />
    """

    handler = HtmlImageHandler()
    new_html, results = await handler.process_images(html, mock_upload)

    print(f"Images processed: {len(results)}")
    for i, result in enumerate(results, 1):
        print(f"  Image {i}:")
        print(f"    Status: {result['status']}")
        print(f"    Original: {result['src'][:50]}...")
        if result['new_src']:
            print(f"    New: {result['new_src']}")


async def test_mixed_images():
    """测试混合图片（外链 + base64 + 微信图）。"""
    print("\n=== Test 3: Mixed Images ===")

    html = """
    <p>混合图片测试</p>
    <img src="https://picsum.photos/400/300" alt="外链图1" />
    <img src="https://mmbiz.qpic.cn/existing/image.jpg" alt="已有微信图" />
    <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==" alt="base64" />
    """

    handler = HtmlImageHandler()
    new_html, results = await handler.process_images(html, mock_upload)

    print(f"Images processed: {len(results)}")
    print(f"Expected: 2 (skip WeChat image)")

    for i, result in enumerate(results, 1):
        print(f"  Image {i}:")
        print(f"    Status: {result['status']}")
        print(f"    Original: {result['src'][:50]}...")


async def test_image_optimization():
    """测试图片优化。"""
    print("\n=== Test 4: Image Optimization ===")

    processor = ImageProcessor()

    # 创建一个测试图片（白色 1000x1000）
    from PIL import Image
    import io

    img = Image.new("RGB", (1000, 1000), color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    original_data = buffer.getvalue()

    print(f"Original size: {len(original_data) / 1024:.1f} KB")

    # 优化
    optimized = processor.optimize_for_wechat(original_data)
    print(f"Optimized size: {len(optimized) / 1024:.1f} KB")
    print(f"Compression ratio: {len(optimized) / len(original_data) * 100:.1f}%")


async def main():
    """运行所有测试。"""
    print("=" * 60)
    print("微信图片处理功能测试")
    print("=" * 60)

    try:
        await test_external_image()
    except Exception as e:
        print(f"Test 1 failed: {e}")

    try:
        await test_base64_image()
    except Exception as e:
        print(f"Test 2 failed: {e}")

    try:
        await test_mixed_images()
    except Exception as e:
        print(f"Test 3 failed: {e}")

    try:
        await test_image_optimization()
    except Exception as e:
        print(f"Test 4 failed: {e}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
