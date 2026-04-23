#!/usr/bin/env python3
"""Tải video Douyin (抖音) từ link chia sẻ, không có watermark nếu có thể.

Cách dùng:
    python3 douyin_downloader.py "https://v.douyin.com/ltVY25xQeBQ/"
    python3 douyin_downloader.py "3.02 复制打开抖音... https://v.douyin.com/ltVY25xQeBQ/ ..."
    python3 douyin_downloader.py <url> -o ./downloads
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
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
    print(f"[1/5] Link chia sẻ: {share_url}")
    os.makedirs(out_dir, exist_ok=True)

    # Path 1: yt-dlp với cookie Chrome — robust nhất, maintainer cộng đồng fix liên tục
    try:
        return download_with_ytdlp(share_url, out_dir)
    except Exception as exc:
        print(f"  yt-dlp không dùng được: {exc}")

    # Path 2: Playwright headless — để chính browser thật tính a_bogus
    try:
        return download_with_playwright(share_url, out_dir)
    except Exception as exc:
        print(f"  Playwright không dùng được: {exc}")

    # Path 3: logic requests thô (dễ fail vì Douyin yêu cầu a_bogus)
    try:
        video_id, _ = resolve_video_id(share_url)
        print(f"[raw] Video ID: {video_id}")
        info = fetch_video_info(video_id)
        title = info.get("desc") or info.get("description") or video_id
        video_url = pick_video_url(info)
        name = filename or sanitize_filename(f"{video_id}_{title}", video_id) + ".mp4"
        out_path = os.path.join(out_dir, name)
        download_video(video_url, out_path)
        print("✓ Hoàn tất qua requests.")
        return out_path
    except Exception as exc:
        print(f"  requests thất bại: {exc}")

    # Path 4: f2 CLI (có sẵn trước đó)
    return download_with_f2(share_url, out_dir)


def download_with_ytdlp(share_url: str, out_dir: str) -> str:
    """Path chính: yt-dlp tự dùng cookie từ Chrome của user."""
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("Không có `yt-dlp` trong PATH. Cài: pip install -U yt-dlp")
    tmpl = os.path.join(out_dir, "%(id)s_%(title).60B.%(ext)s")
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", "chrome",
        "--no-playlist",
        "--no-part",
        "-f", "best[ext=mp4]/best",
        "-o", tmpl,
        "--print", "after_move:filepath",
        share_url,
    ]
    print(f"[2/5] $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"yt-dlp exit {result.returncode}\nstderr: {result.stderr[-600:]}"
        )
    path = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if not path or not os.path.exists(path):
        raise RuntimeError("yt-dlp không in ra filepath hợp lệ")
    print(f"✓ Hoàn tất qua yt-dlp: {path}")
    return path


def download_with_playwright(share_url: str, out_dir: str) -> str:
    """Fallback: headless Chromium đọc _ROUTER_DATA rồi tự tải."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("Cài: pip install playwright && playwright install chromium") from e

    captured_video_url: list[str] = []

    def on_response(resp):
        url = resp.url
        ct = (resp.headers or {}).get("content-type", "")
        if "douyinvod.com" in url or "video/tos" in url or ct.startswith("video/"):
            if url.endswith(".mp4") or "mime_type=video_mp4" in url or ct.startswith("video/"):
                captured_video_url.append(url)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.on("response", on_response)
        print(f"[3/5] Playwright mở: {share_url}")
        try:
            page.goto(share_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"  goto timeout (bỏ qua, tiếp tục): {e}")
        try:
            page.wait_for_function(
                "window._ROUTER_DATA || document.getElementById('RENDER_DATA')",
                timeout=30000,
            )
        except Exception:
            pass
        # Cho page chạy thêm để video URL được request
        page.wait_for_timeout(4000)
        aweme = page.evaluate(
            """() => {
                const data = window._ROUTER_DATA || (() => {
                    const t = document.getElementById('RENDER_DATA');
                    return t ? JSON.parse(decodeURIComponent(t.textContent)) : null;
                })();
                if (!data) return null;
                const loader = data.loaderData || data;
                for (const v of Object.values(loader)) {
                    if (!v || typeof v !== 'object') continue;
                    if (v.aweme?.detail) return v.aweme.detail;
                    if (v.videoInfoRes?.item_list?.[0]) return v.videoInfoRes.item_list[0];
                    if (v.aweme?.awemeDetail) return v.aweme.awemeDetail;
                }
                return null;
            }"""
        )
        cookies = ctx.cookies()
        browser.close()

    video_url = pick_video_url(aweme) if aweme else None
    if not video_url and captured_video_url:
        video_url = captured_video_url[-1]
        print(f"  Dùng URL capture được từ network: {video_url[:80]}...")
    if not video_url:
        raise RuntimeError(
            f"Không lấy được URL video. aweme={bool(aweme)}, captured={len(captured_video_url)}"
        )
    aweme = aweme or {}
    title = aweme.get("desc") or aweme.get("description") or aweme.get("aweme_id", "video")
    vid = aweme.get("aweme_id") or aweme.get("awemeId") or "video"
    out_path = os.path.join(out_dir, sanitize_filename(f"{vid}_{title}", vid) + ".mp4")
    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": "https://www.douyin.com/",
        "Cookie": cookie_header,
    }
    with requests.get(video_url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                f.write(chunk)
    print(f"✓ Hoàn tất qua Playwright: {out_path}")
    return out_path


def download_with_f2(share_url: str, out_dir: str) -> str:
    """Fallback: dùng CLI `f2 douyin one_video` — xử lý signature Douyin đầy đủ."""
    if shutil.which("f2") is None:
        raise RuntimeError(
            "Không có `f2` trong PATH. Cài: `pip install f2`, rồi chạy lại."
        )
    os.makedirs(out_dir, exist_ok=True)
    cmd = ["f2", "douyin", "one_video", "-u", share_url, "-p", out_dir]
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"f2 thất bại (exit {result.returncode}):\n"
            f"stdout: {result.stdout[-500:]}\nstderr: {result.stderr[-500:]}"
        )
    mp4s = sorted(
        glob.glob(os.path.join(out_dir, "**", "*.mp4"), recursive=True),
        key=os.path.getmtime,
        reverse=True,
    )
    if not mp4s:
        raise RuntimeError(f"f2 chạy xong nhưng không tìm thấy mp4 trong {out_dir}")
    print(f"✓ Hoàn tất qua f2: {mp4s[0]}")
    return mp4s[0]


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
