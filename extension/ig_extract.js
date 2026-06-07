/* ── Instagram 一次性媒体提取脚本 ── */
/* 通过 chrome.scripting.executeScript 注入，提取后立即销毁 */
/* 不调用 IG API，只读取浏览器已渲染的 DOM 元素 */

(function () {
  const result = {
    url: location.href,
    title: "",
    author: "",
    platform: "instagram",
    media_items: [],  // {url, is_video}
    thumbnail: "",
  };

  // 作者：从 URL 提取
  const parts = location.pathname.split("/").filter(Boolean);
  if (parts.length >= 1) {
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

  // 视频：og:video 或 <video> 标签
  const ogVideo = document.querySelector("meta[property='og:video']");
  if (ogVideo && ogVideo.content) {
    result.media_items.push({ url: ogVideo.content, is_video: true });
  }

  // 页面上的 <video> 元素
  const videos = document.querySelectorAll("video");
  for (const v of videos) {
    const src = v.src || v.querySelector("source")?.src || "";
    if (src && src.startsWith("http") && !result.media_items.some(m => m.url === src)) {
      result.media_items.push({ url: src, is_video: true });
    }
  }

  // 图片：og:image（如果没有视频）
  if (result.media_items.length === 0 && result.thumbnail) {
    result.media_items.push({ url: result.thumbnail, is_video: false });
  }

  // 轮播帖：尝试从页面 JSON 数据提取
  if (result.media_items.length <= 1) {
    try {
      // Instagram 页面中可能包含 _sharedData 或 additionalData
      const scripts = document.querySelectorAll("script[type='application/ld+json']");
      for (const s of scripts) {
        const data = JSON.parse(s.textContent);
        if (data.video) {
          const videoUrl = typeof data.video === "string" ? data.video : data.video.contentUrl;
          if (videoUrl && !result.media_items.some(m => m.url === videoUrl)) {
            result.media_items.push({ url: videoUrl, is_video: true });
          }
        }
        if (data.image && result.media_items.length === 0) {
          const imgUrl = typeof data.image === "string" ? data.image : (Array.isArray(data.image) ? data.image[0] : data.image.url);
          if (imgUrl) {
            result.media_items.push({ url: imgUrl, is_video: false });
          }
        }
      }
    } catch {}
  }

  return result;
})();
