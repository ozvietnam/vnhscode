"""Gọi Douyin Web API trực tiếp bằng chữ ký a_bogus — không cần browser."""
from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import quote, urlencode

import requests

from .abogus import ABogus

USERAGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

BASE_WEB_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": "1",
    "version_code": "190500",
    "version_name": "19.5.0",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "MacIntel",
    "browser_name": "Chrome",
    "browser_version": "121.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "121.0.0.0",
    "os_name": "Mac OS",
    "os_version": "10.15.7",
    "cpu_core_num": "8",
    "device_memory": "8",
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "round_trip_time": "50",
}

SHORT_URL_RE = re.compile(r"https?://v\.douyin\.com/[\w\-]+/?")
VIDEO_ID_RE = re.compile(r"/(?:video|note|share/(?:video|slides))/(\d+)")


def extract_share_url(text: str) -> str:
    m = SHORT_URL_RE.search(text)
    if m:
        return m.group(0)
    m = re.search(r"https?://www\.douyin\.com/[^\s]+", text)
    if m:
        return m.group(0)
    raise ValueError(f"Không tìm thấy link Douyin: {text!r}")


def resolve_video_id(share_url: str, session: requests.Session) -> tuple[str, str]:
    resp = session.get(share_url, allow_redirects=True, timeout=20)
    final = resp.url
    m = VIDEO_ID_RE.search(final) or VIDEO_ID_RE.search(resp.text)
    if not m:
        raise RuntimeError(f"Không trích được video_id từ {final}")
    return m.group(1), final


def ensure_session_cookies(session: requests.Session) -> None:
    """Visit douyin.com to get ttwid + __ac_nonce."""
    if session.cookies.get("ttwid"):
        return
    try:
        session.get("https://www.douyin.com/", timeout=15, allow_redirects=True)
    except requests.RequestException:
        pass


def fetch_aweme_detail(aweme_id: str, session: Optional[requests.Session] = None) -> dict:
    """Gọi /aweme/v1/web/aweme/detail/ với a_bogus signature, fallback sang iesdouyin."""
    session = session or requests.Session()
    session.headers.update({
        "User-Agent": USERAGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"https://www.douyin.com/video/{aweme_id}",
    })
    ensure_session_cookies(session)

    # Path 1: Web API với a_bogus (geo-fenced với IP non-CN)
    try:
        return _fetch_web_api(aweme_id, session)
    except Exception as e1:
        first_err = str(e1)

    # Path 2: iesdouyin.com share page → parse RENDER_DATA (đôi khi qua geo-fence)
    try:
        return _fetch_iesdouyin_share(aweme_id, session)
    except Exception as e2:
        # Path 3: iesdouyin iteminfo API (legacy mobile)
        try:
            return _fetch_iesdouyin_iteminfo(aweme_id, session)
        except Exception as e3:
            raise RuntimeError(
                f"Cả 3 API đều fail.\n"
                f"  web a_bogus: {first_err}\n"
                f"  iesdouyin share: {e2}\n"
                f"  iesdouyin iteminfo: {e3}\n"
                f"Khả năng cao IP server bị geo-fence — deploy API ở region Asia."
            )


def _fetch_web_api(aweme_id: str, session: requests.Session) -> dict:
    params = dict(BASE_WEB_PARAMS)
    params["aweme_id"] = aweme_id
    bogus = ABogus().get_value(params)
    params["a_bogus"] = bogus
    url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?" + urlencode(params, quote_via=quote)
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    if not resp.text.strip():
        raise RuntimeError("empty body (geo-fence)")
    data = resp.json()
    detail = data.get("aweme_detail") or data.get("item_list", [None])[0]
    if not detail:
        raise RuntimeError(f"no aweme_detail; keys={list(data.keys())[:6]}")
    return detail


def _fetch_iesdouyin_share(aweme_id: str, session: requests.Session) -> dict:
    """Parse RENDER_DATA từ trang share."""
    url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
        ),
    }
    resp = session.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    html = resp.text
    if not html.strip():
        raise RuntimeError("share page empty")
    m = re.search(r'<script[^>]+id="RENDER_DATA"[^>]*>([^<]+)</script>', html)
    if not m:
        raise RuntimeError("không có RENDER_DATA")
    import json as _json
    from urllib.parse import unquote
    payload = _json.loads(unquote(m.group(1)))
    # Tìm aweme bằng walk
    return _find_aweme_in_dict(payload)


def _fetch_iesdouyin_iteminfo(aweme_id: str, session: requests.Session) -> dict:
    """Legacy mobile API."""
    url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={aweme_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone) Mobile",
        "Referer": f"https://www.iesdouyin.com/share/video/{aweme_id}/",
    }
    resp = session.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    if not resp.text.strip():
        raise RuntimeError("empty body")
    data = resp.json()
    items = data.get("item_list") or []
    if not items:
        raise RuntimeError("item_list rỗng")
    return items[0]


def _find_aweme_in_dict(obj, depth: int = 0):
    """Walk recursive tìm object có aweme_id + video."""
    if depth > 8 or obj is None:
        return None
    if isinstance(obj, dict):
        if ("aweme_id" in obj or "awemeId" in obj) and ("video" in obj or "images" in obj):
            return obj
        for k in ("aweme_detail", "awemeDetail", "aweme", "detail", "item_list", "videoInfoRes"):
            if k in obj:
                v = obj[k]
                found = _find_aweme_in_dict(v[0] if isinstance(v, list) and v else v, depth + 1)
                if found:
                    return found
        for v in obj.values():
            found = _find_aweme_in_dict(v, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_aweme_in_dict(v, depth + 1)
            if found:
                return found
    return None


def download_file(url: str, path: str, session: requests.Session) -> int:
    headers = {"User-Agent": USERAGENT, "Referer": "https://www.douyin.com/"}
    with session.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        size = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                size += len(chunk)
    return size


def search_keyword(
    keyword: str,
    session: Optional[requests.Session] = None,
    offset: int = 0,
    count: int = 15,
    sort_type: int = 0,  # 0=综合, 1=最多点赞, 2=最新
) -> dict:
    """Search Douyin video theo từ khóa. Trả {items, cursor, has_more}."""
    session = session or requests.Session()
    session.headers.update({
        "User-Agent": USERAGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"https://www.douyin.com/search/{quote(keyword)}",
    })
    ensure_session_cookies(session)

    params = dict(BASE_WEB_PARAMS)
    params.update({
        "keyword": keyword,
        "search_channel": "aweme_video_web",
        "sort_type": str(sort_type),
        "publish_time": "0",
        "search_source": "normal_search",
        "query_correct_type": "1",
        "is_filter_search": "0",
        "from_group_id": "",
        "offset": str(offset),
        "count": str(count),
    })
    bogus = ABogus().get_value(params)
    params["a_bogus"] = bogus

    url = "https://www.douyin.com/aweme/v1/web/general/search/single/?" + urlencode(params, quote_via=quote)
    resp = session.get(url, timeout=25)
    resp.raise_for_status()
    if not resp.text.strip():
        raise RuntimeError("Search API trả empty (signature fail hoặc IP bị chặn)")
    data = resp.json()
    items = []
    for row in data.get("data") or []:
        aw = row.get("aweme_info") or row.get("aweme")
        if aw and aw.get("aweme_id"):
            items.append(aw)
    return {
        "items": items,
        "cursor": data.get("cursor", offset + count),
        "has_more": bool(data.get("has_more")),
    }


def search_hashtag(
    hashtag_id: str,
    session: Optional[requests.Session] = None,
    cursor: int = 0,
    count: int = 15,
) -> dict:
    """Search video theo hashtag ID (challenge ID). Trả {items, cursor, has_more}."""
    session = session or requests.Session()
    session.headers.update({"User-Agent": USERAGENT, "Referer": "https://www.douyin.com/"})
    ensure_session_cookies(session)

    params = dict(BASE_WEB_PARAMS)
    params.update({
        "ch_id": hashtag_id,
        "cursor": str(cursor),
        "count": str(count),
        "type": "5",
    })
    bogus = ABogus().get_value(params)
    params["a_bogus"] = bogus

    url = "https://www.douyin.com/aweme/v1/web/challenge/aweme/?" + urlencode(params, quote_via=quote)
    resp = session.get(url, timeout=25)
    resp.raise_for_status()
    if not resp.text.strip():
        raise RuntimeError("Hashtag API trả empty")
    data = resp.json()
    items = [x for x in (data.get("aweme_list") or []) if x.get("aweme_id")]
    return {
        "items": items,
        "cursor": data.get("cursor", cursor + count),
        "has_more": bool(data.get("has_more")),
    }


def pick_video_url(aweme: dict) -> Optional[str]:
    """Chọn URL mp4 không watermark, ưu tiên bitrate cao."""
    video = aweme.get("video") or {}
    # bit_rate list — tập các variants, chọn cái bitrate cao nhất
    br_list = video.get("bit_rate") or []
    if isinstance(br_list, list) and br_list:
        best = max(br_list, key=lambda b: b.get("bit_rate", 0))
        play = best.get("play_addr") or {}
        urls = play.get("url_list") or []
        if urls:
            return urls[0]
    # fallback: play_addr_h264 / play_addr / download_addr
    for key in ("play_addr_h264", "play_addr", "download_addr"):
        block = video.get(key) or {}
        urls = block.get("url_list") if isinstance(block, dict) else None
        if urls:
            return urls[0].replace("playwm", "play")
    return None
