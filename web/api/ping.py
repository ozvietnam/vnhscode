"""Vercel: GET /api/ping — health check từng layer để chẩn đoán."""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status = {"ok": True, "checks": {}, "env": {}}

        # Env info
        status["env"]["python"] = sys.version.split()[0]
        status["env"]["platform"] = sys.platform
        status["env"]["cwd"] = os.getcwd()
        status["env"]["file"] = __file__
        try:
            status["env"]["listdir_parent"] = sorted(os.listdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        except Exception as e:
            status["env"]["listdir_parent"] = f"err: {e}"

        # 1. requests
        try:
            import requests
            status["checks"]["requests"] = "v" + requests.__version__
        except Exception as e:
            status["ok"] = False
            status["checks"]["requests"] = f"FAIL: {type(e).__name__}: {e}"

        # 2. gmssl + pycryptodomex
        try:
            from gmssl import sm3
            status["checks"]["gmssl_sm3"] = "ok"
        except Exception as e:
            status["ok"] = False
            status["checks"]["gmssl_sm3"] = f"FAIL: {type(e).__name__}: {e}"

        # 3. douyin_crawler import — cần include douyin_crawler/ cùng function
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from douyin_crawler import api as dapi
            status["checks"]["crawler_import"] = "ok"
            bogus = dapi.ABogus().get_value({"aid": "6383", "aweme_id": "123"})
            status["checks"]["abogus_gen"] = f"{len(bogus)} chars"
        except Exception as e:
            status["ok"] = False
            status["checks"]["crawler_import"] = f"FAIL: {type(e).__name__}: {e}"

        # 4. Có reach douyin.com không (kiểm tra geo-fence)
        try:
            import requests as _r
            t0 = time.time()
            r = _r.get("https://www.douyin.com/", timeout=8,
                       headers={"User-Agent": "Mozilla/5.0"})
            ms = int((time.time() - t0) * 1000)
            status["checks"]["douyin_reach"] = f"HTTP {r.status_code}, {len(r.content)}B, {ms}ms"
            # Kiểm tra geofence: IP non-CN thường nhận response có text 'abnormal' / 'verify'
            txt = r.text[:500].lower()
            if r.status_code != 200 or "verify" in txt or "abnormal" in txt or "error" in txt[:50]:
                status["checks"]["douyin_geo"] = "LIKELY BLOCKED (geo/bot detection)"
            else:
                status["checks"]["douyin_geo"] = "looks OK"
        except Exception as e:
            status["checks"]["douyin_reach"] = f"FAIL: {type(e).__name__}: {e}"

        body = json.dumps(status, indent=2, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
