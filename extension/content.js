/* ── Lumio Content Script ── */
/* 在 YouTube / X / B站 / 快手 / 小红书 页面注入，提取页面元数据 */
/* Instagram 不注入（避免触发自动化检测，由 background 一次性注入 ig_extract.js） */
/* 抖音/微博网页版不适合用浏览器插件发送，已移除支持（后端 Provider 仍可通过 URL 解析） */

(function () {
  "use strict";

  const hostname = window.location.hostname;
  const href = window.location.href;

  function detectPlatform() {
    if (hostname.includes("youtube.com") || hostname.includes("youtu.be")) return "youtube";
    if (hostname.includes("x.com") || hostname.includes("twitter.com")) return "x";
    if (hostname.includes("bilibili.com") || hostname.includes("b23.tv")) return "bilibili";
    if (hostname.includes("kuaishou.com")) return "kuaishou";
    if (hostname.includes("xiaohongshu.com")) return "xiaohongshu";
    return "";
  }

  // ── 通用元数据提取（og 标签 fallback）──────────────────────────────

  function meta(prop) {
    const el = document.querySelector(`meta[property='${prop}']`) ||
               document.querySelector(`meta[name='${prop}']`);
    return el?.content || "";
  }

  function commonOg() {
    return {
      title: meta("og:title") || document.title,
      thumbnail: meta("og:image") || "",
      author: "",
      duration: null,
    };
  }

  // ── YouTube ──────────────────────────────────────────────────────

  function extractYouTube() {
    const url = window.location.href;
    if (!url.includes("/watch")) return null;

    const videoId = new URL(url).searchParams.get("v") || "";

    const title =
      meta("og:title") ||
      meta("title") ||
      document.title.replace(" - YouTube", "").trim();

    const author =
      document.querySelector("ytd-channel-name yt-formatted-string a")?.textContent?.trim() ||
      document.querySelector("link[itemprop='name']")?.content ||
      meta("author") ||
      document.querySelector("span[itemprop='author'] link[itemprop='name']")?.content ||
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

    const thumbnail =
      meta("og:image") ||
      (videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : "");

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

    const title = meta("og:title") || meta("description") || document.title;

    // 修复 author 提取：排除 i/search/home/notifications/explore 等非用户路径
    // X 推文 URL 格式：x.com/{username}/status/{id}
    // 但通知/搜索场景可能是 x.com/i/status/{id}（username 缺失）
    const pathParts = window.location.pathname.split("/").filter(Boolean);
    const reservedPrefixes = ["i", "search", "home", "notifications", "explore",
                              "settings", "messages", "compose", "hashtag", "topics"];
    let author = "";
    if (pathParts.length >= 2 && pathParts[1] === "status" &&
        !reservedPrefixes.includes(pathParts[0])) {
      author = pathParts[0];
    }

    const thumbnail = meta("og:image") || "";

    // ── 提取真实媒体直链 ──────────────────────────────────────
    // AGENTS.md 明确：video.twimg.com 直链永久有效，不需要 Referer/Cookie 鉴权
    // X 视频 player 直接挂 mp4 src（非 blob:），可直接提取
    // X 图片在 pbs.twimg.com/media/，附加 ?format=jpg&name=orig 拿原图
    const media_items = [];
    const seenUrls = new Set();

    // 视频：遍历 <video> 元素，过滤出 video.twimg.com 直链
    const videos = document.querySelectorAll("video");
    for (const v of videos) {
      const candidates = [
        v.src,
        v.querySelector("source")?.src,
        v.currentSrc,
      ].filter(u => u && u.startsWith("http") && !u.startsWith("blob:") &&
                    u.includes("twimg.com"));
      for (const u of candidates) {
        if (!seenUrls.has(u)) {
          seenUrls.add(u);
          media_items.push({ url: u, is_video: true });
        }
      }
    }

    // 图片：遍历 <img>，匹配 pbs.twimg.com/media/ URL
    // 附加 ?format=jpg&name=orig 拿原图（AGENTS.md "X 图片下载"）
    const imgs = document.querySelectorAll("img[src*='pbs.twimg.com/media/']");
    for (const img of imgs) {
      let imgUrl = img.src.split("?")[0];  // 去掉现有 query 参数
      if (imgUrl) {
        const origUrl = `${imgUrl}?format=jpg&name=orig`;
        if (!seenUrls.has(origUrl)) {
          seenUrls.add(origUrl);
          media_items.push({ url: origUrl, is_video: false });
        }
      }
    }

    // duration：从 <video> 元素读取（秒）
    let duration = null;
    if (videos.length > 0 && videos[0].duration && isFinite(videos[0].duration)) {
      duration = Math.round(videos[0].duration);
    }

    return {
      url, title, author, thumbnail, platform: "x",
      media_items, duration,
      // 传 direct_url 兼容旧逻辑（单媒体场景）
      direct_url: media_items.length > 0 ? media_items[0].url : "",
    };
  }

  // ── B站 ──────────────────────────────────────────────────────────

  function extractBilibili() {
    const url = window.location.href;
    // 仅在视频页提取（/video/BV... 或 /video/av...）
    if (!/\/video\/(BV|av)/i.test(url)) return null;

    const title = meta("og:title") || document.title.replace("_哔哩哔哩_bilibili", "").trim();
    // 作者：UP 主名。优先 meta itemid
    const author =
      document.querySelector("meta[itemprop='name']")?.content ||
      document.querySelector("a.up-name")?.textContent?.trim() ||
      (function () {
        try {
          // initial state 中有 up 信息
          const state = window.__INITIAL_STATE__;
          if (state && state.upData && state.upData.name) return state.upData.name;
        } catch {}
        return "";
      })() ||
      "";
    const thumbnail = meta("og:image") || "";
    // 时长（秒）：从 __INITIAL_STATE__ 提取
    let duration = null;
    try {
      const state = window.__INITIAL_STATE__;
      if (state && state.videoData && state.videoData.duration) {
        duration = parseInt(state.videoData.duration) || null;
      }
    } catch {}

    return { url, title, author, thumbnail, duration, platform: "bilibili" };
  }

  // ── 快手 ──────────────────────────────────────────────────────────

  function extractKuaishou() {
    const url = window.location.href;
    // 短视频页 /short-video/... 或图文页
    if (!/\/(short-video|new-reco|profile)/.test(url)) return null;

    const info = commonOg();
    return { url, title: info.title, author: info.author, thumbnail: info.thumbnail, platform: "kuaishou" };
  }

  // ── 小红书 ────────────────────────────────────────────────────────

  function extractXiaohongshu() {
    const url = window.location.href;
    // 笔记页 /explore/{id} 或 /discovery/item/{id}
    if (!/\/(explore|discovery\/item)\//.test(url)) return null;

    const info = commonOg();
    // 作者：从页面提取
    let author =
      (function () {
        try {
          // 小红书作者通常在 .author-wrapper 或 [data-v-...] 元素中
          const el = document.querySelector(".author-wrapper .username") ||
                     document.querySelector("[class*='author'] [class*='name']");
          if (el) return el.textContent?.trim() || "";
        } catch {}
        return "";
      })() ||
      "";
    // 标题：小红书的 og:title 通常就是笔记标题
    const title = info.title || document.title.replace(" - 小红书", "").trim();

    return { url, title, author, thumbnail: info.thumbnail, platform: "xiaohongshu" };
  }

  // ── 主逻辑 ───────────────────────────────────────────────────────

  function extract() {
    const platform = detectPlatform();
    if (!platform) return null;

    // 先尝试提取详细元数据（仅详情页有）
    let detailed = null;
    switch (platform) {
      case "youtube": detailed = extractYouTube(); break;
      case "x": detailed = extractX(); break;
      case "bilibili": detailed = extractBilibili(); break;
      case "kuaishou": detailed = extractKuaishou(); break;
      case "xiaohongshu": detailed = extractXiaohongshu(); break;
    }

    // 详情页：返回完整元数据
    if (detailed) return detailed;

    // 非详情页（如首页/用户主页/搜索页）：返回基本信息
    // 让 Lumio 收到后自行判断是否可解析
    return {
      url: window.location.href,
      title: document.title || "",
      platform: platform,
      source: "browser",
      type: "url",
    };
  }

  const data = extract();
  if (data) {
    chrome.runtime.sendMessage({ type: "pageInfo", data }).catch(() => {});
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "extractNow") {
      const fresh = extract();
      // 始终返回数据（非支持平台返回 null）
      sendResponse(fresh);
      return true;
    }
  });
})();
