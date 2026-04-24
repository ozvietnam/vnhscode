const $ = (s) => document.querySelector(s);
const URL_RE = /https?:\/\/(?:v\.douyin\.com|www\.douyin\.com|www\.iesdouyin\.com)\/[^\s<>"']+/gi;

const urlsEl = $("#urls");
const fileEl = $("#file");
const scanBtn = $("#scan");
const statusEl = $("#status");
const results = $("#results");
const tmpl = $("#card-tmpl");

function extractUrls(text) {
  const found = (text || "").match(URL_RE) || [];
  return [...new Set(found.map((u) => u.replace(/[.,;:!?)"']+$/, "")))];
}

function setStatus(msg, isErr = false) {
  statusEl.textContent = msg;
  statusEl.classList.toggle("err", !!isErr);
}

function fmtNum(n) {
  if (n == null) return "";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function renderCard(item) {
  const node = tmpl.content.cloneNode(true);
  const card = node.querySelector(".card");

  if (item.error) {
    card.classList.add("error");
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
  cover.src = item.cover_url || "";
  cover.alt = item.title || "";

  card.querySelector(".title").textContent = item.title || item.id;
  card.querySelector(".author").textContent = item.author ? "@" + item.author : "";
  card.querySelector(".stats").textContent = [
    item.stats?.likes != null ? `❤ ${fmtNum(item.stats.likes)}` : null,
    item.stats?.comments != null ? `💬 ${fmtNum(item.stats.comments)}` : null,
    item.stats?.plays != null ? `▶ ${fmtNum(item.stats.plays)}` : null,
  ].filter(Boolean).join(" · ");

  const tagsBox = card.querySelector(".hashtags");
  tagsBox.innerHTML = "";
  (item.hashtags || []).slice(0, 6).forEach((t) => {
    const el = document.createElement("span");
    el.textContent = "#" + t;
    tagsBox.appendChild(el);
  });

  const links = {
    video: { el: card.querySelector(".video"), url: item.video_url, name: `${item.id}.mp4` },
    "cover-dl": { el: card.querySelector(".cover-dl"), url: item.cover_url, name: `${item.id}.jpg` },
    audio: { el: card.querySelector(".audio"), url: item.audio_url, name: `${item.id}.mp3` },
    subtitle: { el: card.querySelector(".subtitle"), url: item.subtitle_url, name: `${item.id}.srt` },
  };
  for (const [k, v] of Object.entries(links)) {
    if (v.url) {
      v.el.href = `/api/proxy?url=${encodeURIComponent(v.url)}&name=${encodeURIComponent(v.name)}`;
    } else {
      v.el.classList.add("hidden");
    }
  }

  card.querySelector(".all").onclick = () => {
    for (const v of Object.values(links)) {
      if (v.url) v.el.click();
    }
  };
  results.appendChild(node);
}

async function scan() {
  const text = urlsEl.value;
  const urls = extractUrls(text);
  if (!urls.length) {
    setStatus("Không tìm thấy link Douyin trong nội dung dán.", true);
    return;
  }
  results.innerHTML = "";
  setStatus(`Đang scan ${urls.length} link...`);
  scanBtn.disabled = true;
  try {
    const r = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls }),
    });
    if (!r.ok) throw new Error(`API ${r.status}`);
    const data = await r.json();
    const items = data.items || [];
    items.forEach(renderCard);
    const ok = items.filter((i) => !i.error).length;
    setStatus(`✓ Xong — ${ok}/${items.length} thành công`);
  } catch (e) {
    setStatus("Scan lỗi: " + e.message, true);
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
  setStatus(`Đã load ${f.name} — nhấn Scan`);
};

// Drag & drop file vào textarea
urlsEl.addEventListener("dragover", (e) => { e.preventDefault(); urlsEl.classList.add("drag"); });
urlsEl.addEventListener("dragleave", () => urlsEl.classList.remove("drag"));
urlsEl.addEventListener("drop", async (e) => {
  e.preventDefault();
  urlsEl.classList.remove("drag");
  const f = e.dataTransfer.files?.[0];
  if (f) urlsEl.value = await f.text();
});
