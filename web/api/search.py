"""Vercel: GET /api/search?q=<kw>&type=keyword|hashtag&offset=0&count=15"""
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

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


def _aweme_to_card(aweme: dict) -> dict:
    video = aweme.get("video") or {}
    music = aweme.get("music") or {}
    stats = aweme.get("statistics") or {}
    author = aweme.get("author") or {}
    captions = aweme.get("caption_infos") or []
    return {
        "id": aweme.get("aweme_id"),
        "title": aweme.get("desc") or aweme.get("aweme_id"),
        "author": author.get("nickname"),
        "cover_url": _first_url(video.get("cover") or video.get("origin_cover")),
        "video_url": dapi.pick_video_url(aweme),
        "audio_url": _first_url(music.get("play_url")),
        "subtitle_url": captions[0].get("url") if captions else None,
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

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        keyword = (q.get("q") or [""])[0].strip()
        stype = (q.get("type") or ["keyword"])[0]
        offset = int((q.get("offset") or ["0"])[0] or 0)
        count = min(int((q.get("count") or ["15"])[0] or 15), 30)

        if not keyword:
            return self._send(400, {"error": "q (keyword/hashtag) required"})

        try:
            if stype == "hashtag":
                res = dapi.search_hashtag(keyword, cursor=offset, count=count)
            else:
                res = dapi.search_keyword(keyword, offset=offset, count=count)
            items = [_aweme_to_card(a) for a in res["items"]]
            self._send(200, {
                "items": items,
                "cursor": res["cursor"],
                "has_more": res["has_more"],
            })
        except Exception as e:
            self._send(500, {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-600:]})
