/* ── Lumio Content Script ── */
/* 在 YouTube / X 页面注入，提取页面元数据 */
/* Instagram 不注入（避免触发自动化检测） */

(function () {
  "use strict";

  const hostname = window.location.hostname;

  function detectPlatform() {
    if (hostname.includes("youtube.com")) return "youtube";
    if (hostname.includes("x.com") || hostname.includes("twitter.com")) return "x";
    return "";
  }

  // ── YouTube ──────────────────────────────────────────────────────

  function extractYouTube() {
    const url = window.location.href;
    if (!url.includes("/watch")) return null;

    // 提取视频 ID
    const videoId = new URL(url).searchParams.get("v") || "";

    // 标题：优先 og:title，其次 document.title
    const title =
      document.querySelector("meta[property='og:title']")?.content ||
      document.querySelector("meta[name='title']")?.content ||
      document.title.replace(" - YouTube", "").trim();

    // 作者：多层选择器 fallback
    const author =
      document.querySelector("ytd-channel-name yt-formatted-string a")?.textContent?.trim() ||
      document.querySelector("link[itemprop='name']")?.content ||
      document.querySelector("meta[name='author']")?.content ||
      document.querySelector("span[itemprop='author'] link[itemprop='name']")?.content ||
      // 从 structured data 提取
      (function () {
        try {
          const ld = document.querySelector('script[type="application/ld+json"]');
          if (ld) {
            const data = JSON.parse(ld.textContent);
            if (data.author) {
              return Array.isArray(data.author) ? data.author[0]?.name : data.author?.name || "";
            }
          }
        } catch {}
        return "";
      })() ||
      "";

    // 缩略图：优先 og:image，fallback 到 YouTube 标准缩略图 URL
    const thumbnail =
      document.querySelector("meta[property='og:image']")?.content ||
      (videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : "");

    // 时长
    let duration = null;
    try {
      const ld = document.querySelector('script[type="application/ld+json"]');
      if (ld) {
        const data = JSON.parse(ld.textContent);
        if (data.duration) {
          const m = data.duration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
          if (m) {
            duration = (parseInt(m[1] || 0) * 3600) + (parseInt(m[2] || 0) * 60) + parseInt(m[3] || 0);
          }
        }
      }
    } catch {}

    return { url, title, author, thumbnail, duration, platform: "youtube" };
  }

  // ── X (Twitter) ──────────────────────────────────────────────────

  function extractX() {
    const url = window.location.href;
    if (!/\/status\/\d+/.test(url)) return null;

    const title =
      document.querySelector("meta[property='og:title']")?.content ||
      document.querySelector("meta[name='description']")?.content ||
      document.title;

    const author = window.location.pathname.split("/")[1] || "";

    const thumbnail =
      document.querySelector("meta[property='og:image']")?.content || "";

    return { url, title, author, thumbnail, platform: "x" };
  }

  // ── 主逻辑 ───────────────────────────────────────────────────────

  function extract() {
    const platform = detectPlatform();
    switch (platform) {
      case "youtube": return extractYouTube();
      case "x": return extractX();
      default: return null;
    }
  }

  const data = extract();
  if (data) {
    chrome.runtime.sendMessage({ type: "pageInfo", data }).catch(() => {});
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "extractNow") {
      const fresh = extract();
      sendResponse(fresh || { error: "Not a supported page" });
    }
  });
})();
