(function () {
  function findRouterData() {
    if (window._ROUTER_DATA) return window._ROUTER_DATA;
    var tag = document.getElementById("RENDER_DATA");
    if (tag) {
      try { return JSON.parse(decodeURIComponent(tag.textContent)); } catch (e) {}
    }
    return null;
  }
  function pickAweme(data) {
    var loader = (data && data.loaderData) || data;
    for (var k in loader) {
      var v = loader[k];
      if (!v || typeof v !== "object") continue;
      if (v.aweme && v.aweme.detail) return v.aweme.detail;
      if (v.videoInfoRes && v.videoInfoRes.item_list && v.videoInfoRes.item_list[0]) return v.videoInfoRes.item_list[0];
      if (v.aweme && v.aweme.awemeDetail) return v.aweme.awemeDetail;
    }
    return null;
  }
  function pickUrl(aw) {
    var v = (aw && aw.video) || {};
    var keys = ["play_addr", "playAddr", "play_addr_h264", "download_addr"];
    for (var i = 0; i < keys.length; i++) {
      var b = v[keys[i]];
      if (!b) continue;
      var list = b.url_list || b.urlList || [];
      if (list.length) return String(list[0]).replace("playwm", "play");
    }
    return null;
  }
  function sanitize(n) { return (n || "douyin").replace(/[\\/:*?"<>|\r\n\t]/g, "_").slice(0, 80); }

  var data = findRouterData();
  if (!data) return alert("Không tìm thấy _ROUTER_DATA. Đợi trang load xong rồi thử lại.");
  var aw = pickAweme(data);
  if (!aw) { console.log("[dy]", data); return alert("Không trích được metadata. Xem console."); }
  var url = pickUrl(aw);
  if (!url) { console.log("[dy]", aw); return alert("Không tìm được URL video. Xem console."); }
  var id = aw.aweme_id || aw.awemeId || "video";
  var desc = aw.desc || aw.description || "";
  var name = sanitize(id + "_" + desc) + ".mp4";
  var a = document.createElement("a");
  a.href = url; a.download = name; a.target = "_blank"; a.rel = "noopener";
  document.body.appendChild(a); a.click(); a.remove();
  console.log("[dy] downloading", url, "->", name);
})();
