"""Vercel Python serverless: GET /api/proxy?url=<cdn_url>&name=<filename>

Stream file từ Douyin CDN → browser, set Content-Disposition để save as tên gọn.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from douyin_crawler import api as dapi  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        url = (q.get("url") or [None])[0]
        name = (q.get("name") or ["file"])[0]
        if not url:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"url required")
            return

        import requests
        try:
            r = requests.get(
                url,
                headers={"User-Agent": dapi.USERAGENT, "Referer": "https://www.douyin.com/"},
                stream=True,
                timeout=45,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"CDN fetch fail: {e}".encode())
            return

        ct = r.headers.get("Content-Type", "application/octet-stream")
        cl = r.headers.get("Content-Length")
        self.send_response(200)
        self.send_header("Content-Type", ct)
        if cl:
            self.send_header("Content-Length", cl)
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
