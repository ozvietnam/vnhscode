#!/usr/bin/env python3
"""Tải video Douyin (抖音) từ link chia sẻ, không có watermark nếu có thể.

Cách dùng:
    python3 douyin_downloader.py "https://v.douyin.com/ltVY25xQeBQ/"
    python3 douyin_downloader.py "3.02 复制打开抖音... https://v.douyin.com/ltVY25xQeBQ/ ..."
    python3 douyin_downloader.py <url> -o ./downloads
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from typing import Optional

import requests

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SHORT_URL_RE = re.compile(r"https?://v\.douyin\.com/[\w\-]+/?")
VIDEO_ID_RE = re.compile(r"/(?:video|note)/(\d+)")


def extract_share_url(text: str) -> str:
    """Rút URL v.douyin.com hoặc www.douyin.com từ đoạn text chia sẻ."""
    m = SHORT_URL_RE.search(text)
    if m:
        return m.group(0)
    m = re.search(r"https?://www\.douyin\.com/[^\s]+", text)
    if m:
        return m.group(0)
    raise ValueError(f"Không tìm thấy link Douyin trong: {text!r}")


def resolve_video_id(share_url: str) -> tuple[str, str]:
    """Theo redirect của link chia sẻ để lấy video_id và URL cuối cùng."""
    session = requests.Session()
    session.headers.update({"User-Agent": MOBILE_UA})
    resp = session.get(share_url, allow_redirects=True, timeout=15)
    final_url = resp.url
    m = VIDEO_ID_RE.search(final_url)
    if not m:
        m = VIDEO_ID_RE.search(resp.text)
    if not m:
        raise RuntimeError(f"Không trích xuất được video_id từ: {final_url}")
    return m.group(1), final_url


def fetch_video_info(video_id: str) -> dict:
    """Gọi endpoint iteminfo của Douyin để lấy metadata video."""
    api = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={video_id}"
    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": f"https://www.iesdouyin.com/share/video/{video_id}/",
    }
    resp = requests.get(api, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("item_list") or []
    if items:
        return items[0]
    return _fetch_via_share_page(video_id)


def _fetch_via_share_page(video_id: str) -> dict:
    """Fallback: parse JSON nhúng trong trang share."""
    url = f"https://www.iesdouyin.com/share/video/{video_id}/"
    headers = {"User-Agent": MOBILE_UA}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    m = re.search(
        r'<script[^>]+id="RENDER_DATA"[^>]*>([^<]+)</script>', resp.text
    )
    if not m:
        raise RuntimeError("Không lấy được dữ liệu video từ trang share")
    decoded = urllib.parse.unquote(m.group(1))
    payload = json.loads(decoded)
    for value in payload.values():
        if isinstance(value, dict) and "aweme" in value:
            aweme = value["aweme"]
            detail = aweme.get("detail") or aweme.get("awemeDetail")
            if detail:
                return detail
    raise RuntimeError("Không parse được cấu trúc RENDER_DATA")


def pick_video_url(info: dict) -> str:
    """Chọn URL phát video chất lượng cao, ưu tiên bản không watermark."""
    video = info.get("video") or {}
    for key in ("play_addr", "playAddr", "play_addr_h264", "download_addr"):
        block = video.get(key)
        if not block:
            continue
        if isinstance(block, list) and block:
            return block[0].get("src") or block[0].get("url") or block[0]
        url_list = block.get("url_list") or block.get("urlList") or []
        if url_list:
            # Replace playwm → play để lấy bản không watermark
            return url_list[0].replace("playwm", "play")
    raise RuntimeError("Không tìm được URL phát video trong metadata")


def sanitize_filename(name: str, fallback: str) -> str:
    name = (name or "").strip() or fallback
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]", "_", name)
    return name[:80] or fallback


def download_video(url: str, out_path: str) -> None:
    headers = {"User-Agent": DESKTOP_UA, "Referer": "https://www.douyin.com/"}
    with requests.get(url, headers=headers, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        written = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)
                if total:
                    pct = written * 100 / total
                    sys.stdout.write(f"\r  Đang tải: {pct:5.1f}% ({written}/{total} B)")
                    sys.stdout.flush()
        if total:
            sys.stdout.write("\n")


def download(share_text: str, out_dir: str = ".", filename: Optional[str] = None) -> str:
    share_url = extract_share_url(share_text)
    print(f"[1/4] Link chia sẻ: {share_url}")

    video_id, final_url = resolve_video_id(share_url)
    print(f"[2/4] Video ID   : {video_id}")

    info = fetch_video_info(video_id)
    title = info.get("desc") or info.get("description") or video_id
    author = (info.get("author") or {}).get("nickname", "")
    print(f"[3/4] Tiêu đề    : {title[:60]}  —  tác giả: {author}")

    video_url = pick_video_url(info)
    os.makedirs(out_dir, exist_ok=True)
    name = filename or sanitize_filename(f"{video_id}_{title}", video_id) + ".mp4"
    out_path = os.path.join(out_dir, name)

    print(f"[4/4] Lưu vào    : {out_path}")
    download_video(video_url, out_path)
    print("✓ Hoàn tất.")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Tải video Douyin từ link chia sẻ")
    parser.add_argument("url", help="Link v.douyin.com hoặc đoạn text chia sẻ")
    parser.add_argument("-o", "--out", default=".", help="Thư mục lưu (mặc định: .)")
    parser.add_argument("-n", "--name", help="Tên file tùy chọn")
    args = parser.parse_args()

    try:
        download(args.url, args.out, args.name)
    except Exception as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
