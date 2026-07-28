/**
 * Instagram 媒体提取（content script 模块）
 *
 * ★ 改为常驻 content script（不再用 executeScript 一次性注入）
 * 原因：executeScript + files 不等待 async Promise，导致返回 undefined
 *
 * ★ 实测发现（2026-07）：
 *   1. IG 头像 URL 路径含 t51.82787-19（非 t51.2885-19）
 *   2. 帖子媒体 URL 路径含 t51.82787-15
 *   3. /embed/ 端点可匿名访问，但只返回部分图（多图帖子）
 *   4. DOM 提取需要等待 SPA 渲染（5-10s）
 *   5. DOM 优先（已登录时完整），embed 兜底（未登录时）
 */
import type { MediaItem } from "../types";
import type { ExtractResult } from "./shared/types";

/** 判断是否为头像 URL */
function isAvatarUrl(url: string, alt?: string): boolean {
  if (url.includes("t51.82787-19") || url.includes("t51.2885-19")) return true;
  if (alt && (alt.includes("头像") || alt.toLowerCase().includes("avatar") || alt.toLowerCase().includes("profile"))) return true;
  return false;
}

/** 判断是否为小尺寸缩略图 */
function isSmallThumbnail(url: string): boolean {
  return (
    url.includes("s100x100") ||
    url.includes("s150x150") ||
    url.includes("s320x320")
  );
}

/** 等待 DOM 媒体元素出现 */
function waitForMedia(maxWait = 10000, interval = 200): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now();
    function check() {
      const hasVideo = document.querySelectorAll("video").length > 0;
      const hasImg =
        document.querySelectorAll(
          "img[src*='cdninstagram'], img[src*='fbcdn']",
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

export async function extractInstagram(): Promise<ExtractResult | null> {
  const url = window.location.href;
  // 仅在 /p/ 或 /reel/ 页提取
  if (!/\/(p|reel)\//.test(url)) return null;

  const parts = location.pathname.split("/").filter(Boolean);
  let author = "";
  if (parts.length >= 2 && (parts[1] === "p" || parts[1] === "reel")) {
    author = parts[0];
  }

  const title =
    document.querySelector("meta[property='og:title']")?.getAttribute("content") ||
    document.querySelector("meta[name='description']")?.getAttribute("content") ||
    "Instagram post";

  const ogImage =
    document.querySelector("meta[property='og:image']")?.getAttribute("content") || "";

  const media_items: MediaItem[] = [];
  const seenUrls = new Set<string>();

  function addMedia(rawUrl: string, isVideo: boolean, alt?: string): boolean {
    if (!rawUrl || !rawUrl.startsWith("http")) return false;
    if (rawUrl.startsWith("blob:")) return false;
    if (!rawUrl.includes("fbcdn") && !rawUrl.includes("cdninstagram")) return false;
    if (isAvatarUrl(rawUrl, alt)) return false;
    if (!isVideo && isSmallThumbnail(rawUrl)) return false;
    if (seenUrls.has(rawUrl)) return false;
    seenUrls.add(rawUrl);
    media_items.push({ url: rawUrl, is_video: isVideo });
    return true;
  }

  // ── 优先级 1：DOM 提取（已登录时完整）──────────────────────────
  await waitForMedia(8000, 200);

  // 视频
  const ogVideo = document.querySelector("meta[property='og:video']");
  const ogVideoContent = ogVideo?.getAttribute("content");
  if (ogVideoContent) addMedia(ogVideoContent, true);

  const videos = document.querySelectorAll("video");
  for (const v of Array.from(videos)) {
    const candidates = [v.src, v.querySelector("source")?.src || "", v.currentSrc];
    for (const u of candidates) addMedia(u, true);
  }

  // 图片：DOM 所有 fbcdn/cdninstagram 图片
  const cdnImgs = document.querySelectorAll(
    "img[src*='cdninstagram'], img[src*='fbcdn']",
  );
  for (const img of Array.from(cdnImgs)) {
    const src = img.getAttribute("src");
    const alt = img.getAttribute("alt") || "";
    if (!src) continue;
    addMedia(src, false, alt);
  }

  // srcset 图片（取最高分辨率）
  const srcsetImgs = document.querySelectorAll(
    "img[srcset*='cdninstagram'], img[srcset*='fbcdn']",
  );
  for (const img of Array.from(srcsetImgs)) {
    const srcset = img.getAttribute("srcset") || "";
    const alt = img.getAttribute("alt") || "";
    if (srcset) {
      const entries = srcset.split(",").map((s) => s.trim()).filter(Boolean);
      if (entries.length > 0) {
        const last = entries[entries.length - 1].split(/\s+/)[0];
        if (last && last.startsWith("http")) addMedia(last, false, alt);
      }
    }
  }

  // ── 优先级 2：/embed/ 兜底（DOM 没找到时）──────────────────────
  if (media_items.length === 0) {
    let shortcode = "";
    for (let i = 0; i < parts.length - 1; i++) {
      if (parts[i] === "p" || parts[i] === "reel") {
        shortcode = parts[i + 1];
        break;
      }
    }
    if (shortcode) {
      try {
        const isReel = parts[0] === "reel" || parts[1] === "reel";
        const embedPath = isReel ? `/reel/${shortcode}/embed/` : `/p/${shortcode}/embed/`;
        const resp = await fetch(embedPath, { credentials: "omit" });
        if (resp.ok) {
          const html = await resp.text();
          const doc = new DOMParser().parseFromString(html, "text/html");
          const embedVideos = doc.querySelectorAll("video");
          for (const v of Array.from(embedVideos)) {
            const candidates = [v.src, v.querySelector("source")?.src || "", v.currentSrc];
            for (const u of candidates) addMedia(u, true);
          }
          const embedImgs = doc.querySelectorAll(
            "img[src*='fbcdn'], img[src*='cdninstagram']",
          );
          for (const img of Array.from(embedImgs)) {
            const imgUrl = img.getAttribute("src");
            const imgAlt = img.getAttribute("alt") || "";
            if (!imgUrl) continue;
            addMedia(imgUrl, false, imgAlt);
          }
        }
      } catch (e) {
        console.log("IG embed failed:", e);
      }
    }
  }

  // 兜底：og:image
  if (media_items.length === 0 && ogImage && !isAvatarUrl(ogImage)) {
    addMedia(ogImage, false);
  }

  const thumbnail = media_items.find((m) => !m.is_video)?.url || ogImage;

  return {
    url,
    title,
    author,
    thumbnail,
    platform: "instagram",
    media_items,
    duration: null,
    direct_url: media_items.length > 0 ? media_items[0].url : "",
  };
}
