// ==UserScript==
// @name         Douyin Video Downloader
// @namespace    https://github.com/ozvietnam/vnhscode
// @version      0.1.0
// @description  Tải video Douyin (không watermark) trực tiếp từ Chrome — không cần server, dùng session/cookie hiện tại của browser.
// @match        https://www.douyin.com/*
// @match        https://www.iesdouyin.com/*
// @match        https://v.douyin.com/*
// @run-at       document-idle
// @grant        GM_download
// @grant        GM_xmlhttpRequest
// @connect      *
// ==/UserScript==

(function () {
  "use strict";

  const log = (...a) => console.log("[douyin-dl]", ...a);

  function findRouterData() {
    if (window._ROUTER_DATA) return window._ROUTER_DATA;
    const tag = document.getElementById("RENDER_DATA");
    if (tag) {
      try {
        return JSON.parse(decodeURIComponent(tag.textContent));
      } catch (e) {
        log("RENDER_DATA parse fail", e);
      }
    }
    return null;
  }

  function pickAweme(data) {
    const loader = data?.loaderData || data;
    for (const v of Object.values(loader || {})) {
      if (!v || typeof v !== "object") continue;
      if (v.aweme?.detail) return v.aweme.detail;
      if (v.videoInfoRes?.item_list?.[0]) return v.videoInfoRes.item_list[0];
      if (v.aweme?.awemeDetail) return v.aweme.awemeDetail;
    }
    return null;
  }

  function pickVideoUrl(aweme) {
    const v = aweme?.video || {};
    for (const key of ["play_addr", "playAddr", "play_addr_h264", "download_addr"]) {
      const block = v[key];
      if (!block) continue;
      const list = block.url_list || block.urlList || [];
      if (list.length) return list[0].replace("playwm", "play");
    }
    return null;
  }

  function sanitize(name) {
    return (name || "douyin")
      .replace(/[\\/:*?"<>|\r\n\t]/g, "_")
      .slice(0, 80);
  }

  function triggerDownload(url, filename) {
    if (typeof GM_download === "function") {
      GM_download({ url, name: filename, saveAs: true });
      return;
    }
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.target = "_blank";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function makeButton() {
    if (document.getElementById("__dy_dl_btn")) return;
    const btn = document.createElement("button");
    btn.id = "__dy_dl_btn";
    btn.textContent = "⬇ Tải video";
    Object.assign(btn.style, {
      position: "fixed",
      right: "16px",
      bottom: "16px",
      zIndex: 999999,
      padding: "10px 14px",
      background: "#fe2c55",
      color: "#fff",
      border: "none",
      borderRadius: "8px",
      fontSize: "14px",
      fontWeight: "600",
      cursor: "pointer",
      boxShadow: "0 4px 12px rgba(0,0,0,.25)",
    });
    btn.onclick = onDownloadClick;
    document.body.appendChild(btn);
  }

  function onDownloadClick() {
    const data = findRouterData();
    if (!data) {
      alert("Không tìm thấy _ROUTER_DATA. Đợi trang load xong rồi thử lại.");
      return;
    }
    const aweme = pickAweme(data);
    if (!aweme) {
      alert("Không trích được metadata video từ _ROUTER_DATA. Có thể Douyin đã đổi cấu trúc.");
      console.log("[douyin-dl] router data:", data);
      return;
    }
    const url = pickVideoUrl(aweme);
    if (!url) {
      alert("Không tìm được URL phát video.");
      console.log("[douyin-dl] aweme:", aweme);
      return;
    }
    const id = aweme.aweme_id || aweme.awemeId || "video";
    const desc = aweme.desc || aweme.description || "";
    const filename = sanitize(`${id}_${desc}`) + ".mp4";
    log("downloading", url, "→", filename);
    triggerDownload(url, filename);
  }

  // Mount button when video page is detected
  const mount = () => {
    if (location.pathname.startsWith("/video/") || location.hostname === "v.douyin.com") {
      makeButton();
    }
  };
  mount();
  new MutationObserver(mount).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();
