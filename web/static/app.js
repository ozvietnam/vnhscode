const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const URL_RE = /https?:\/\/(?:v\.douyin\.com|www\.douyin\.com|www\.iesdouyin\.com)\/[^\s<>"']+/gi;

const urlsEl = $("#urls");
const fileEl = $("#file");
const scanBtn = $("#scan");
const statusEl = $("#status");
const results = $("#results");
const tmpl = $("#card-tmpl");

const searchQ = $("#searchQ");
const searchType = $("#searchType");
const searchSort = $("#searchSort");
const searchBtn = $("#searchBtn");
const searchStatus = $("#searchStatus");
const loadMoreWrap = $("#loadMoreWrap");
const loadMoreBtn = $("#loadMore");

const bulkbar = $("#bulkbar");
const selectAll = $("#selectAll");
const selectedCount = $("#selectedCount");
const totalCount = $("#totalCount");

let searchCursor = 0;
let currentQuery = null;

// ---- Tab switching ----
$$(".tab").forEach((t) => {
  t.onclick = () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    $$(".pane").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $(`.pane[data-pane="${t.dataset.tab}"]`).classList.add("active");
  };
});

// ---- Utilities ----
function extractUrls(text) {
  const found = (text || "").match(URL_RE) || [];
  return [...new Set(found.map((u) => u.replace(/[.,;:!?)"']+$/, "")))];
}

function setStatus(el, msg, isErr = false) {
  el.textContent = msg;
  el.classList.toggle("err", !!isErr);
}

function fmtNum(n) {
  if (n == null) return "";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function updateSelectCounts() {
  const picks = $$(".card .pick:checked");
  selectedCount.textContent = picks.length;
  const all = $$(".card .pick");
  totalCount.textContent = all.length;
  bulkbar.classList.toggle("hidden", all.length === 0);
  selectAll.checked = all.length > 0 && picks.length === all.length;
}

// ---- Render ----
function renderCard(item) {
  const node = tmpl.content.cloneNode(true);
  const card = node.querySelector(".card");

  if (item.error) {
    card.classList.add("error");
    card.querySelector(".select").remove();
    card.querySelector("img.cover").remove();
    card.querySelector(".title").textContent = "Lỗi: " + (item.url || "");
    card.querySelector(".author").textContent = "";
    card.querySelector(".stats").textContent = item.error;
    card.querySelector(".hashtags").remove();
    card.querySelector(".actions").remove();
    results.appendChild(node);
    return;
  }

  const cover = card.querySelector("img.cover");
  cover.src = item.cover_url ? `/api/proxy?url=${encodeURIComponent(item.cover_url)}&name=cover.jpg` : "";
  cover.alt = item.title || "";
  cover.onerror = () => { cover.src = item.cover_url || ""; };

  card.querySelector(".title").textContent = item.title || item.id;
  card.querySelector(".author").textContent = item.author ? "@" + item.author : "";
  card.querySelector(".stats").textContent = [
    item.stats?.likes != null ? `❤ ${fmtNum(item.stats.likes)}` : null,
    item.stats?.comments != null ? `💬 ${fmtNum(item.stats.comments)}` : null,
    item.stats?.plays != null ? `▶ ${fmtNum(item.stats.plays)}` : null,
  ].filter(Boolean).join(" · ");

  const tagsBox = card.querySelector(".hashtags");
  (item.hashtags || []).slice(0, 6).forEach((t) => {
    const el = document.createElement("span");
    el.textContent = "#" + t;
    tagsBox.appendChild(el);
  });

  const links = {
    video: { el: card.querySelector(".video"), url: item.video_url, name: `${item.id}.mp4` },
    cover: { el: card.querySelector(".cover-dl"), url: item.cover_url, name: `${item.id}.jpg` },
    audio: { el: card.querySelector(".audio"), url: item.audio_url, name: `${item.id}.mp3` },
    subtitle: { el: card.querySelector(".subtitle"), url: item.subtitle_url, name: `${item.id}.srt` },
  };
  for (const [, v] of Object.entries(links)) {
    if (v.url) {
      v.el.href = `/api/proxy?url=${encodeURIComponent(v.url)}&name=${encodeURIComponent(v.name)}`;
    } else {
      v.el.classList.add("hidden");
    }
  }

  card.querySelector(".all").onclick = () => {
    for (const v of Object.values(links)) if (v.url) v.el.click();
  };

  const pick = card.querySelector(".pick");
  pick.dataset.item = JSON.stringify({
    id: item.id,
    urls: Object.fromEntries(Object.entries(links).map(([k, v]) => [k, v.url ? v.el.href : null])),
  });
  pick.onchange = updateSelectCounts;

  results.appendChild(node);
}

// ---- Paste / Scan ----
async function scan() {
  const text = urlsEl.value;
  const urls = extractUrls(text);
  if (!urls.length) return setStatus(statusEl, "Không tìm thấy link Douyin.", true);
  results.innerHTML = "";
  loadMoreWrap.classList.add("hidden");
  setStatus(statusEl, `Đang scan ${urls.length} link...`);
  scanBtn.disabled = true;
  try {
    const r = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls }),
    });
    if (!r.ok) throw new Error(`API ${r.status}`);
    const data = await r.json();
    (data.items || []).forEach(renderCard);
    const ok = (data.items || []).filter((i) => !i.error).length;
    setStatus(statusEl, `✓ ${ok}/${(data.items || []).length} thành công`);
    updateSelectCounts();
  } catch (e) {
    setStatus(statusEl, "Scan lỗi: " + e.message, true);
  } finally {
    scanBtn.disabled = false;
  }
}

scanBtn.onclick = scan;
urlsEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) scan();
});
fileEl.onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  urlsEl.value = await f.text();
  setStatus(statusEl, `Đã load ${f.name} — nhấn Scan`);
};
urlsEl.addEventListener("dragover", (e) => { e.preventDefault(); urlsEl.classList.add("drag"); });
urlsEl.addEventListener("dragleave", () => urlsEl.classList.remove("drag"));
urlsEl.addEventListener("drop", async (e) => {
  e.preventDefault();
  urlsEl.classList.remove("drag");
  const f = e.dataTransfer.files?.[0];
  if (f) urlsEl.value = await f.text();
});

// ---- Search ----
async function runSearch(append = false) {
  const q = searchQ.value.trim().replace(/^#/, "");
  if (!q) return setStatus(searchStatus, "Nhập từ khóa hoặc hashtag ID.", true);
  if (!append) {
    results.innerHTML = "";
    searchCursor = 0;
    currentQuery = { q, type: searchType.value, sort: searchSort.value };
  }
  setStatus(searchStatus, `Đang tìm "${currentQuery.q}" (offset=${searchCursor})...`);
  searchBtn.disabled = true;
  loadMoreBtn.disabled = true;
  try {
    const params = new URLSearchParams({
      q: currentQuery.q,
      type: currentQuery.type,
      offset: String(searchCursor),
      count: "15",
    });
    const r = await fetch("/api/search?" + params.toString());
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.error || `API ${r.status}`);
    }
    const data = await r.json();
    const items = data.items || [];
    items.forEach(renderCard);
    searchCursor = data.cursor || searchCursor + items.length;
    setStatus(searchStatus, `✓ Có thêm ${items.length} kết quả (tổng ${$$(".card").length})`);
    loadMoreWrap.classList.toggle("hidden", !data.has_more);
    updateSelectCounts();
  } catch (e) {
    setStatus(searchStatus, "Tìm lỗi: " + e.message, true);
  } finally {
    searchBtn.disabled = false;
    loadMoreBtn.disabled = false;
  }
}

searchBtn.onclick = () => runSearch(false);
loadMoreBtn.onclick = () => runSearch(true);
searchQ.addEventListener("keydown", (e) => {
  if (e.key === "Enter") runSearch(false);
});

// ---- Bulk actions ----
selectAll.onchange = () => {
  $$(".card .pick").forEach((p) => (p.checked = selectAll.checked));
  updateSelectCounts();
};

async function triggerSequential(urls, delayMs = 600) {
  for (const u of urls) {
    const a = document.createElement("a");
    a.href = u;
    a.target = "_blank";
    a.rel = "noopener";
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    a.remove();
    await new Promise((r) => setTimeout(r, delayMs));
  }
}

$$(".btn-bulk").forEach((btn) => {
  btn.onclick = async () => {
    const kind = btn.dataset.kind;
    const urls = [];
    $$(".card .pick:checked").forEach((p) => {
      const item = JSON.parse(p.dataset.item);
      if (item.urls[kind]) urls.push(item.urls[kind]);
    });
    if (!urls.length) return alert("Chưa chọn item nào có " + kind);
    btn.disabled = true;
    const prev = btn.textContent;
    btn.textContent = `⏳ Đang tải ${urls.length}...`;
    await triggerSequential(urls);
    btn.textContent = prev;
    btn.disabled = false;
  };
});
