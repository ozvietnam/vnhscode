"""Vercel Python serverless: POST /api/extract {urls: [...]}."""
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

# Load douyin_crawler từ web/ (đi lên 1 cấp là web/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from douyin_crawler import api as dapi  # noqa: E402


def _first_url(block):
    if not block:
        return None
    if isinstance(block, str):
        return block
    if isinstance(block, list) and block:
        return block[0]
    for k in ("url_list", "urlList"):
        lst = block.get(k) if isinstance(block, dict) else None
        if lst:
            return lst[0]
    return None


def extract_one(share_text_or_url: str) -> dict:
    import requests
    share_url = dapi.extract_share_url(share_text_or_url)
    session = requests.Session()
    session.headers.update({"User-Agent": dapi.USERAGENT})
    try:
        video_id, final_url = dapi.resolve_video_id(share_url, session)
    except Exception as e:
        return {"url": share_text_or_url, "error": f"Resolve fail: {e}"}
    try:
        aweme = dapi.fetch_aweme_detail(video_id, session)
    except Exception as e:
        return {"url": share_url, "id": video_id, "error": f"Fetch detail fail: {e}"}

    video = aweme.get("video") or {}
    music = aweme.get("music") or {}
    stats = aweme.get("statistics") or {}
    author = aweme.get("author") or {}
    captions = aweme.get("caption_infos") or []
    subtitle_url = captions[0].get("url") if captions else None

    return {
        "url": share_url,
        "id": aweme.get("aweme_id") or video_id,
        "title": aweme.get("desc") or video_id,
        "author": author.get("nickname"),
        "cover_url": _first_url(video.get("cover") or video.get("origin_cover")),
        "video_url": dapi.pick_video_url(aweme),
        "audio_url": _first_url(music.get("play_url")),
        "subtitle_url": subtitle_url,
        "hashtags": [t.get("hashtag_name") for t in (aweme.get("text_extra") or []) if t.get("hashtag_name")],
        "stats": {
            "likes": stats.get("digg_count"),
            "comments": stats.get("comment_count"),
            "plays": stats.get("play_count"),
            "shares": stats.get("share_count"),
        },
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            urls = payload.get("urls", [])
            if not isinstance(urls, list) or not urls:
                return self._send(400, {"error": "urls (array) required"})
            items = []
            for u in urls[:20]:  # hạn chế 20 link / request để đỡ timeout
                try:
                    items.append(extract_one(u))
                except Exception as e:
                    items.append({"url": u, "error": f"{type(e).__name__}: {e}"})
            self._send(200, {"items": items})
        except Exception as e:
            self._send(500, {"error": str(e), "trace": traceback.format_exc()[-800:]})
