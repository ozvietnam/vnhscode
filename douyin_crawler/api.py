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
    """Gọi /aweme/v1/web/aweme/detail/ với a_bogus signature."""
    session = session or requests.Session()
    session.headers.update({
        "User-Agent": USERAGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"https://www.douyin.com/video/{aweme_id}",
    })
    ensure_session_cookies(session)

    params = dict(BASE_WEB_PARAMS)
    params["aweme_id"] = aweme_id

    bogus = ABogus().get_value(params)
    params["a_bogus"] = bogus

    url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?" + urlencode(params, quote_via=quote)
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    body = resp.text
    if not body.strip():
        raise RuntimeError("Douyin trả empty body (signature fail hoặc bị block)")
    data = resp.json()
    detail = data.get("aweme_detail") or data.get("item_list", [None])[0]
    if not detail:
        raise RuntimeError(f"Response không có aweme_detail: keys={list(data.keys())[:6]}")
    return detail


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
