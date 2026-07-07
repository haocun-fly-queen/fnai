"""
微博 Cookie 自动获取服务（Windows 本地运行）

启动方式：
  python weibo_cookie_service.py

服务会在 http://localhost:5001 启动，前端调用获取 Cookie。
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

try:
    from selenium import webdriver
except ImportError:
    print("[错误] 缺少 selenium，请安装：pip install selenium")
    exit(1)


LOGIN_URL = "https://passport.weibo.cn/signin/login"
PORT = 5001


def find_browser():
    """自动检测浏览器"""
    try:
        from selenium.webdriver.edge.options import Options
        return "edge", Options()
    except ImportError:
        pass
    try:
        from selenium.webdriver.chrome.options import Options
        return "chrome", Options()
    except ImportError:
        pass
    return None, None


def get_cookie_async(callback):
    """异步获取 Cookie，完成后调用 callback(cookie_str, error)"""
    def task():
        browser_type, options = find_browser()
        if not browser_type:
            callback(None, "未检测到 Chrome 或 Edge 浏览器")
            return

        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        print(f"[信息] 启动 {browser_type.upper()} 浏览器...")
        if browser_type == "edge":
            driver = webdriver.Edge(options=options)
        else:
            driver = webdriver.Chrome(options=options)

        try:
            driver.get(LOGIN_URL)
            print("[信息] 请在浏览器中登录微博...")

            max_wait = 300
            start = time.time()

            while time.time() - start < max_wait:
                url = driver.current_url
                if "m.weibo.cn" in url and "login" not in url and "passport" not in url:
                    time.sleep(2)
                    cookies = driver.get_cookies()
                    if cookies:
                        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                        callback(cookie_str, None)
                        return
                time.sleep(1)

            callback(None, "登录超时（5分钟）")
        except Exception as e:
            callback(None, f"获取失败: {e}")
        finally:
            try:
                driver.quit()
            except:
                pass

    threading.Thread(target=task, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    pending = False
    result = None

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            self.send_json({"status": "ok"})
        elif path == "/get-cookie":
            self.handle_get_cookie()
        elif path == "/check-cookie":
            self.handle_check_cookie()
        else:
            self.send_json({"error": "未知接口"}, 404)

    def handle_get_cookie(self):
        if Handler.pending:
            self.send_json({"error": "正在获取中，请稍候"})
            return

        Handler.result = None
        Handler.pending = True

        def on_done(cookie, error):
            Handler.result = {"cookie": cookie, "error": error}
            Handler.pending = False

        get_cookie_async(on_done)
        self.send_json({"status": "started", "message": "浏览器已打开，请登录微博"})

    def handle_check_cookie(self):
        if Handler.pending:
            self.send_json({"status": "pending", "message": "等待登录中..."})
            return

        if Handler.result:
            r = Handler.result
            Handler.result = None
            if r["cookie"]:
                self.send_json({"status": "success", "cookie": r["cookie"]})
            else:
                self.send_json({"status": "failed", "error": r["error"]})
            return

        self.send_json({"status": "idle"})

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║           微博 Cookie 自动获取服务                           ║
╠══════════════════════════════════════════════════════════════╣
║  服务地址: http://localhost:5001                             ║
║  按 Ctrl+C 停止服务                                          ║
╚══════════════════════════════════════════════════════════════╝
""")
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[信息] 服务已启动: http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[信息] 服务已停止")


if __name__ == "__main__":
    main()
