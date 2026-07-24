"""
Lumio UI Preview Server
启动本地 HTTP 服务预览赛博朋克风 UI 设计，包含 6 种进度条样式对比。
仅用于设计预览，不影响 Lumio 主程序。
"""
import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

PORT = 38999
PREVIEW_DIR = Path(__file__).parent


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PREVIEW_DIR), **kwargs)

    def log_message(self, *args):
        pass  # 静默日志


def main():
    os.chdir(PREVIEW_DIR)
    with socketserver.TCPServer(("127.0.0.1", PORT), PreviewHandler) as httpd:
        url = f"http://127.0.0.1:{PORT}/preview.html"
        print(f"[Lumio UI Preview] 服务已启动: {url}")
        print(f"[Lumio UI Preview] 按 Ctrl+C 停止")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Lumio UI Preview] 已停止")


if __name__ == "__main__":
    main()
