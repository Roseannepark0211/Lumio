/* ── Instagram 一次性媒体提取脚本 ── */
/* 通过 chrome.scripting.executeScript 注入，提取后立即销毁 */
/* 不调用 IG API，只读取浏览器已渲染的 DOM 元素或 /embed/ 端点 */

(async function () {
  const result = {
    url: location.href,
    title: "",
    author: "",
    platform: "instagram",
    media_items: [],  // {url, is_video}
    thumbnail: "",
  };

  // 作者：从 URL 提取（/p/{id} 或 /reel/{id} 时 parts[0] 不是作者，留空让后端补全）
  const parts = location.pathname.split("/").filter(Boolean);
  // IG 详情页 URL 格式：instagram.com/{username}/p/{id} 或 instagram.com/p/{id}
  // 后者 parts[0]="p"，无作者信息；前者 parts[1]="p"，parts[0]=作者
  if (parts.length >= 2 && (parts[1] === "p" || parts[1] === "reel")) {
    result.author = parts[0];
  }

  // 标题：og:title 或 meta description
  result.title =
    document.querySelector("meta[property='og:title']")?.content ||
    document.querySelector("meta[name='description']")?.content ||
    document.title.replace(" • Instagram photos and videos", "").trim() ||
    "Instagram post";

  // 缩略图：og:image
  result.thumbnail =
    document.querySelector("meta[property='og:image']")?.content || "";

  // ── 提取 shortcode（/p/{shortcode}/ 或 /reel/{shortcode}/）────────
  let shortcode = "";
  for (let i = 0; i < parts.length - 1; i++) {
    if (parts[i] === "p" || parts[i] === "reel") {
      shortcode = parts[i + 1];
      break;
    }
  }

  // ── 优先级 1：fetch /embed/ 端点（匿名可访问，含完整 CDN 直链）──────
  // 实测：/p/{shortcode}/embed/ 返回完整 HTML，包含所有 carousel 图片 URL
  // 域名格式：instagram.fhkg4-X.fna.fbcdn.net 或 scontent.cdninstagram.com
  // /reel/{shortcode}/embed/ 同样可用
  if (shortcode) {
    try {
      const embedPath = parts[0] === "reel" || parts[1] === "reel"
        ? `/reel/${shortcode}/embed/`
        : `/p/${shortcode}/embed/`;
      const embedResp = await fetch(embedPath, { credentials: "omit" });
      if (embedResp.ok) {
        const embedHtml = await embedResp.text();
        const doc = new DOMParser().parseFromString(embedHtml, "text/html");

        // embed 页的 og:title / og:image 更可靠
        const embedTitle = doc.querySelector("meta[property='og:title']")?.content;
        if (embedTitle && !result.title) result.title = embedTitle;
        const embedImage = doc.querySelector("meta[property='og:image']")?.content;
        if (embedImage && !result.thumbnail) result.thumbnail = embedImage;

        // 视频：embed 页可能有 <video> 直接挂 mp4 src（非 blob:）
        const embedVideos = doc.querySelectorAll("video");
        for (const v of embedVideos) {
          const candidates = [v.src, v.querySelector("source")?.src, v.currentSrc]
            .filter(u => u && u.startsWith("http") && !u.startsWith("blob:"));
          for (const u of candidates) {
            if (!result.media_items.some(m => m.url === u)) {
              result.media_items.push({ url: u, is_video: true });
            }
          }
        }

        // 图片：从 embed HTML 提取所有 fbcdn/cdninstagram 图片
        // embed 页所有 <img>，筛选 CDN 主图（排除头像 s100x100、grid 预览）
        const embedImgs = doc.querySelectorAll(
          "img[src*='fbcdn.net'], img[src*='cdninstagram.com']"
        );
        const seenUrls = new Set();
        for (const img of embedImgs) {
          let imgUrl = img.src;
          if (!imgUrl) continue;
          // 排除头像（路径含 t51.2885-19 是 profile pic 目录）
          if (imgUrl.includes("t51.2885-19")) continue;
          // 排除小尺寸缩略图
          if (imgUrl.includes("s100x100") || imgUrl.includes("s320x320")) continue;
          // carousel 主图在 t51.82787-15 目录，src 含 stp=dst-jpg_e35
          if (seenUrls.has(imgUrl)) continue;
          seenUrls.add(imgUrl);
          if (!result.media_items.some(m => m.url === imgUrl)) {
            result.media_items.push({ url: imgUrl, is_video: false });
          }
        }
      }
    } catch (e) {
      console.log("IG embed fetch failed:", e);
    }
  }

  // ── 优先级 2：DOM 提取（embed 失败时的兜底）──────────────────────
  if (result.media_items.length === 0) {
    // 等待 SPA 渲染（最多 8 秒，IG graphql 可能需要 3-5 秒）
    await waitForMedia(8000, 150);

    // 视频提取（blob: URL 过滤，只保留 http 直链）
    const videoUrls = new Set();
    const ogVideo = document.querySelector("meta[property='og:video']");
    if (ogVideo && ogVideo.content) {
      videoUrls.add(ogVideo.content);
    }
    const videos = document.querySelectorAll("video");
    for (const v of videos) {
      const candidates = [v.src, v.querySelector("source")?.src, v.currentSrc]
        .filter(u => u && u.startsWith("http") && !u.startsWith("blob:"));
      for (const u of candidates) {
        videoUrls.add(u);
      }
    }
    for (const url of videoUrls) {
      result.media_items.push({ url, is_video: true });
    }

    // 图片提取（增强选择器：srcset + src + picture source）
    const imgUrls = new Set();
    // srcset 匹配（轮播帖主图）
    const carouselImgs = document.querySelectorAll(
      "img[srcset*='cdninstagram'], img[srcset*='fbcdn']"
    );
    for (const img of carouselImgs) {
      const srcset = img.srcset || "";
      if (srcset) {
        const entries = srcset.split(",").map(s => s.trim()).filter(Boolean);
        if (entries.length > 0) {
          const last = entries[entries.length - 1].split(/\s+/)[0];
          if (last && last.startsWith("http")) imgUrls.add(last);
        }
      }
      if (img.src && img.src.startsWith("http") &&
          (img.src.includes("cdninstagram") || img.src.includes("fbcdn"))) {
        imgUrls.add(img.src);
      }
    }
    // src 直接匹配（部分 IG 版本不用 srcset）
    const srcImgs = document.querySelectorAll(
      "img[src*='cdninstagram'], img[src*='fbcdn']"
    );
    for (const img of srcImgs) {
      if (img.src && img.src.startsWith("http")) {
        // 排除头像和小缩略图
        if (img.src.includes("t51.2885-19")) continue;
        if (img.src.includes("s100x100") || img.src.includes("s320x320")) continue;
        imgUrls.add(img.src);
      }
    }
    // picture source 元素（2024+ 可能改用 picture）
    const pictureSources = document.querySelectorAll(
      "picture source[srcset*='fbcdn'], picture source[srcset*='cdninstagram']"
    );
    for (const source of pictureSources) {
      const srcset = source.srcset || "";
      if (srcset) {
        const entries = srcset.split(",").map(s => s.trim()).filter(Boolean);
        if (entries.length > 0) {
          const last = entries[entries.length - 1].split(/\s+/)[0];
          if (last && last.startsWith("http")) imgUrls.add(last);
        }
      }
    }

    // 兜底：og:image
    if (imgUrls.size === 0 && result.thumbnail) {
      imgUrls.add(result.thumbnail);
    }
    for (const url of imgUrls) {
      if (!result.media_items.some(m => m.url === url)) {
        result.media_items.push({ url, is_video: false });
      }
    }
  }

  // ── 最终兜底：至少返回 thumbnail ──────────────────────────
  if (result.media_items.length === 0 && result.thumbnail) {
    result.media_items.push({ url: result.thumbnail, is_video: false });
  }

  // 等待 SPA 渲染函数
  function waitForMedia(maxWait = 8000, interval = 150) {
    return new Promise((resolve) => {
      const start = Date.now();
      function check() {
        const hasVideo = document.querySelectorAll("video").length > 0;
        const hasImg = document.querySelectorAll(
          "img[srcset*='cdninstagram'], img[srcset*='fbcdn'], " +
          "img[src*='cdninstagram'], img[src*='fbcdn'], " +
          "picture source[srcset*='fbcdn']"
        ).length > 0;
        if (hasVideo || hasImg || Date.now() - start >= maxWait) {
          resolve();
          return;
        }
        setTimeout(check, interval);
      }
      check();
    });
  }

  return result;
})();
