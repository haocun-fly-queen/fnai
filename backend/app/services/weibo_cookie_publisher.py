"""
微博自动发文脚本（Cookie 方式，无需 App Key）
通过模拟浏览器请求发微博，只需要你的微博登录 Cookie。

使用方式：
  python weibo_cookie_publisher.py --post "你好，这是一条测试微博"
  python weibo_cookie_publisher.py --post "带图微博" --image photo.jpg
  python weibo_cookie_publisher.py --batch weibo_posts.json
  python weibo_cookie_publisher.py --user-info

获取 Cookie 的方法见下方说明。
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests


# ─────────────────────────── 常量 ───────────────────────────

COOKIE_FILE = "weibo_cookie.txt"
POSTS_FILE = "weibo_posts.json"

# 微博移动端 API（更稳定）
M_WEIBO_BASE = "https://m.weibo.cn"
POST_URL = f"{M_WEIBO_BASE}/api/statuses/update"
USER_URL = f"{M_WEIBO_BASE}/api/config"

# 微博 PC 端 API（支持发图）
PC_WEIBO_BASE = "https://weibo.com"
UPLOAD_PIC_URL = "https://picupload.weibo.com/interface/pic_upload.php"


# ─────────────────────────── Cookie 管理 ───────────────────────────

def save_cookie(cookie_str: str):
    """保存 Cookie 到文件"""
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        f.write(cookie_str.strip())
    print(f"[✓] Cookie 已保存到 {COOKIE_FILE}")


def load_cookie() -> str:
    """从文件加载 Cookie"""
    if not os.path.exists(COOKIE_FILE):
        print(f"[错误] 未找到 Cookie 文件")
        print(f"[提示] 请先获取 Cookie，然后保存到 {COOKIE_FILE}")
        print(f"       或者使用 --set-cookie 参数直接设置")
        sys.exit(1)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookie = f.read().strip()
    if not cookie:
        print("[错误] Cookie 文件为空")
        sys.exit(1)
    return cookie


def get_headers(cookie: str) -> dict:
    """构造请求头"""
    return {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://m.weibo.cn/compose/",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
    }


def get_xsrf_token(cookie: str) -> str:
    """从 Cookie 中提取 XSRF-TOKEN"""
    match = re.search(r"XSRF-TOKEN=([^;]+)", cookie)
    if match:
        return match.group(1)
    return ""


# ─────────────────────────── 获取 Cookie 指引 ───────────────────────────

def print_cookie_guide():
    """打印获取 Cookie 的详细步骤"""
    guide = """
╔══════════════════════════════════════════════════════════════╗
║                    获取微博 Cookie 步骤                       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. 用浏览器打开 https://m.weibo.cn 并登录你的微博账号        ║
║                                                              ║
║  2. 按 F12 打开开发者工具，切换到「网络」(Network) 标签        ║
║                                                              ║
║  3. 刷新页面，在请求列表中点击任意一个请求                    ║
║                                                              ║
║  4. 在右侧「请求头」(Headers) 中找到「Cookie」字段            ║
║                                                              ║
║  5. 复制整个 Cookie 值（很长的一串）                          ║
║                                                              ║
║  6. 运行以下命令保存：                                        ║
║     python weibo_cookie_publisher.py --set-cookie "粘贴内容"  ║
║                                                              ║
║  注意：Cookie 有效期通常较长，但微博修改密码后会失效           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(guide)


# ─────────────────────────── API 调用 ───────────────────────────

def get_user_info(cookie: str) -> dict:
    """获取当前登录用户信息"""
    headers = get_headers(cookie)
    resp = requests.get(USER_URL, headers=headers)
    result = resp.json()
    if result.get("ok") != 1:
        print(f"[错误] 获取用户信息失败，Cookie 可能已过期")
        return {}
    data = result.get("data", {})
    user = data.get("user", {})
    return user


def post_weibo(cookie: str, text: str, image_path: str = None) -> dict:
    """
    发布一条微博。
    使用移动端 API，不需要安全域名。
    """
    headers = get_headers(cookie)
    
    # 添加 XSRF token
    xsrf = get_xsrf_token(cookie)
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf

    data = {"content": text}

    if image_path:
        path = Path(image_path)
        if not path.exists():
            print(f"[错误] 图片不存在: {image_path}")
            return {}
        with open(path, "rb") as f:
            files = {"pic": (path.name, f, "image/jpeg")}
            resp = requests.post(POST_URL, headers=headers, data=data, files=files)
    else:
        resp = requests.post(POST_URL, headers=headers, data=data)

    result = resp.json()
    if result.get("ok") != 1:
        msg = result.get("msg", "未知错误")
        print(f"[错误] 发布失败: {msg}")
        return {}
    return result.get("data", {})


# ─────────────────────────── 批量发布 ───────────────────────────

def batch_post(cookie: str, posts_file: str, interval: int = 60):
    """从 JSON 文件批量发布微博"""
    path = Path(posts_file)
    if not path.exists():
        print(f"[错误] 文件不存在: {posts_file}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        posts = json.load(f)

    if isinstance(posts, dict):
        posts = [posts]

    total = len(posts)
    print(f"\n共 {total} 条微博待发布，间隔 {interval} 秒\n")
    print("-" * 60)

    success = 0
    fail = 0
    for i, post in enumerate(posts):
        text = post.get("text", "")
        image = post.get("image", "")

        print(f"\n[{i+1}/{total}] 发布中...")
        print(f"  内容: {text[:50]}{'...' if len(text) > 50 else ''}")

        result = post_weibo(cookie, text, image if image else None)
        if result and "id" in result:
            weibo_id = result.get("id", "")
            print(f"  [✓] 成功！微博ID: {weibo_id}")
            success += 1
        else:
            fail += 1

        if i < total - 1:
            print(f"  等待 {interval} 秒后发布下一条...")
            time.sleep(interval)

    print(f"\n{'=' * 60}")
    print(f"发布完成：成功 {success} 条，失败 {fail} 条")


# ─────────────────────────── 主流程 ───────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="微博自动发文脚本（Cookie 方式，无需 App Key）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python weibo_cookie_publisher.py --cookie-guide        # 查看获取 Cookie 的步骤
  python weibo_cookie_publisher.py --set-cookie "SUB=..." # 保存 Cookie
  python weibo_cookie_publisher.py --post "你好微博"       # 发一条微博
  python weibo_cookie_publisher.py --post "带图" --image photo.jpg
  python weibo_cookie_publisher.py --batch weibo_posts.json
  python weibo_cookie_publisher.py --user-info
        """,
    )
    parser.add_argument("--cookie-guide", action="store_true", help="显示获取 Cookie 的详细步骤")
    parser.add_argument("--set-cookie", metavar="COOKIE", help="保存 Cookie 到本地文件")
    parser.add_argument("--post", metavar="TEXT", help="发布一条微博")
    parser.add_argument("--image", help="附带的图片路径（可选）")
    parser.add_argument("--batch", metavar="FILE", help="从 JSON 文件批量发布")
    parser.add_argument("--interval", type=int, default=60, help="批量发布间隔秒数（默认60）")
    parser.add_argument("--user-info", action="store_true", help="查看当前登录用户信息")

    args = parser.parse_args()

    # ── 查看 Cookie 获取指引 ──
    if args.cookie_guide:
        print_cookie_guide()
        return

    # ── 保存 Cookie ──
    if args.set_cookie:
        save_cookie(args.set_cookie)
        return

    # ── 以下操作需要 Cookie ──
    cookie = load_cookie()

    # ── 查看用户信息 ──
    if args.user_info:
        user = get_user_info(cookie)
        if user:
            print(f"\n用户信息：")
            print(f"  昵称     : {user.get('screen_name', '')}")
            print(f"  UID      : {user.get('id', '')}")
            print(f"  粉丝数   : {user.get('followers_count', '')}")
            print(f"  关注数   : {user.get('follow_count', '')}")
            print(f"  微博数   : {user.get('statuses_count', '')}")
        return

    # ── 发布单条 ──
    if args.post:
        result = post_weibo(cookie, args.post, args.image)
        if result and "id" in result:
            print(f"[✓] 发布成功！微博ID: {result['id']}")
        return

    # ── 批量发布 ──
    if args.batch:
        batch_post(cookie, args.batch, args.interval)
        return

    # ── 无参数 ──
    parser.print_help()
    print("\n[提示] 首次使用请先获取 Cookie: python weibo_cookie_publisher.py --cookie-guide")


if __name__ == "__main__":
    main()
