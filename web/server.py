"""Flask server — deploy to Fly.io (Singapore) to bypass Douyin geo-fence.

Routes:
  GET  /                     → index.html
  GET  /static/<path>        → static files
  POST /api/extract          → extract aweme from share URLs
  GET  /api/search           → keyword / hashtag search
  GET  /api/proxy            → stream CDN file to browser
  GET  /api/ping             → health check
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

from flask import Flask, Response, jsonify, request, send_from_directory

# Make douyin_crawler importable (server.py lives in web/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from douyin_crawler import api as dapi  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(ROOT, "static"), static_url_path="/static")


# ---------------------------------------------------------------------------
# Static / HTML
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(ROOT, "index.html")


# ---------------------------------------------------------------------------
# Helpers shared by extract + search
# ---------------------------------------------------------------------------

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


def _extract_one(share_text_or_url: str) -> dict:
    import requests as _req
    share_url = dapi.extract_share_url(share_text_or_url)
    session = _req.Session()
    session.headers.update({"User-Agent": dapi.USERAGENT})
    try:
        video_id, _ = dapi.resolve_video_id(share_url, session)
    except Exception as e:
        return {"url": share_text_or_url, "error": f"Resolve fail: {e}"}
    try:
        aweme = dapi.fetch_aweme_detail(video_id, session)
    except Exception as e:
        return {"url": share_url, "id": video_id, "error": f"Fetch detail fail: {e}"}
    card = _aweme_to_card(aweme)
    card["url"] = share_url
    return card


# ---------------------------------------------------------------------------
# POST /api/extract
# ---------------------------------------------------------------------------

@app.route("/api/extract", methods=["POST", "OPTIONS"])
def api_extract():
    if request.method == "OPTIONS":
        return _cors_preflight()
    try:
        payload = request.get_json(force=True, silent=True) or {}
        urls = payload.get("urls", [])
        if not isinstance(urls, list) or not urls:
            return _json({"error": "urls (array) required"}, 400)
        items = []
        for u in urls[:20]:
            try:
                items.append(_extract_one(u))
            except Exception as e:
                items.append({"url": u, "error": f"{type(e).__name__}: {e}"})
        return _json({"items": items})
    except Exception as e:
        return _json({"error": str(e), "trace": traceback.format_exc()[-800:]}, 500)


# ---------------------------------------------------------------------------
# GET /api/search
# ---------------------------------------------------------------------------

@app.route("/api/search")
def api_search():
    keyword = (request.args.get("q") or "").strip()
    stype = request.args.get("type", "keyword")
    offset = int(request.args.get("offset", 0) or 0)
    count = min(int(request.args.get("count", 15) or 15), 30)

    if not keyword:
        return _json({"error": "q (keyword/hashtag) required"}, 400)

    try:
        if stype == "hashtag":
            res = dapi.search_hashtag(keyword, cursor=offset, count=count)
        else:
            res = dapi.search_keyword(keyword, offset=offset, count=count)
        items = [_aweme_to_card(a) for a in res["items"]]
        return _json({"items": items, "cursor": res["cursor"], "has_more": res["has_more"]})
    except Exception as e:
        return _json({"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-600:]}, 500)


# ---------------------------------------------------------------------------
# GET /api/proxy
# ---------------------------------------------------------------------------

@app.route("/api/proxy")
def api_proxy():
    import requests as _req

    url = request.args.get("url")
    name = request.args.get("name", "file")
    if not url:
        return Response("url required", 400)

    try:
        r = _req.get(
            url,
            headers={"User-Agent": dapi.USERAGENT, "Referer": "https://www.douyin.com/"},
            stream=True,
            timeout=45,
        )
        r.raise_for_status()
    except _req.RequestException as e:
        return Response(f"CDN fetch fail: {e}", 502, content_type="text/plain; charset=utf-8")

    ct = r.headers.get("Content-Type", "application/octet-stream")
    cl = r.headers.get("Content-Length")

    def generate():
        for chunk in r.iter_content(64 * 1024):
            if chunk:
                yield chunk

    headers = {
        "Content-Type": ct,
        "Content-Disposition": f'attachment; filename="{name}"',
        "Access-Control-Allow-Origin": "*",
    }
    if cl:
        headers["Content-Length"] = cl
    return Response(generate(), headers=headers)


# ---------------------------------------------------------------------------
# GET /api/ping
# ---------------------------------------------------------------------------

@app.route("/api/ping")
def api_ping():
    status = {"ok": True, "checks": {}, "env": {}}
    status["env"]["python"] = sys.version.split()[0]
    status["env"]["platform"] = sys.platform
    status["env"]["cwd"] = os.getcwd()

    # requests
    try:
        import requests as _req
        status["checks"]["requests"] = "v" + _req.__version__
    except Exception as e:
        status["ok"] = False
        status["checks"]["requests"] = f"FAIL: {e}"

    # gmssl
    try:
        from gmssl import sm3  # noqa: F401
        status["checks"]["gmssl_sm3"] = "ok"
    except Exception as e:
        status["ok"] = False
        status["checks"]["gmssl_sm3"] = f"FAIL: {e}"

    # crawler + abogus
    try:
        bogus = dapi.ABogus().get_value({"aid": "6383", "aweme_id": "123"})
        status["checks"]["abogus_gen"] = f"{len(bogus)} chars"
    except Exception as e:
        status["ok"] = False
        status["checks"]["crawler_import"] = f"FAIL: {e}"

    # Douyin reachability
    try:
        import requests as _req
        t0 = time.time()
        r = _req.get("https://www.douyin.com/", timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        ms = int((time.time() - t0) * 1000)
        status["checks"]["douyin_reach"] = f"HTTP {r.status_code}, {len(r.content)}B, {ms}ms"
        txt = r.text[:500].lower()
        if r.status_code != 200 or "verify" in txt or "abnormal" in txt:
            status["checks"]["douyin_geo"] = "LIKELY BLOCKED"
        else:
            status["checks"]["douyin_geo"] = "OK"
    except Exception as e:
        status["checks"]["douyin_reach"] = f"FAIL: {e}"

    return _json(status)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(obj, code=200):
    body = json.dumps(obj, ensure_ascii=False, indent=2)
    resp = Response(body, status=code, content_type="application/json; charset=utf-8")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def _cors_preflight():
    resp = Response("", 204)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
