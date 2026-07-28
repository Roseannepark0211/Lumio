/**
 * X (Twitter) 元数据提取
 * - 仅在 /status/{id} 页提取
 * - ★ 区域限定：只取主推文（main 下第一个 article），不抓评论区
 * - 视频直链：video.twimg.com（永久有效，无需鉴权）
 * - 图片直链：pbs.twimg.com/media/<id>?format=jpg&name=orig
 *
 * ★ 多图 carousel 处理：
 *   X 多图推文用 carousel 组件，DOM 中只渲染当前可见的图
 *   其他图需要：
 *   1. 查 [data-testid="tweetPhoto"] 容器内的 img
 *   2. 查 background-image 含 pbs.twimg.com/media/ 的元素
 *   3. 查所有 article 内的 pbs.twimg.com/media/（兜底）
 */
import { meta } from "../shared/og";
import type { ExtractResult } from "../shared/types";
import type { MediaItem } from "../../types";

/** 定位主推文元素 */
function getMainTweet(): Element | null {
  const mainArticle = document.querySelector(
    "main[role='main'] article[role='article']",
  );
  if (mainArticle) return mainArticle;
  const primaryCol = document.querySelector(
    '[data-testid="primaryColumn"] article[role="article"]',
  );
  if (primaryCol) return primaryCol;
  return document.querySelector("article[role='article']");
}

/**
 * 将 X 图片 URL 转为原图 URL
 *
 * 实测格式：
 *   https://pbs.twimg.com/media/HOUiy6kXwAAoQQk?format=jpg&name=medium
 *
 * 原图：替换 name 参数为 orig
 */
function toOrigImageUrl(url: string): string {
  if (!url) return url;
  const baseUrl = url.split("?")[0];
  // 已有 ?format=xxx&name=xxx → 替换 name 为 orig
  if (url.includes("format=") && url.includes("name=")) {
    return `${baseUrl}?format=jpg&name=orig`;
  }
  // 检测是否已有扩展名
  const hasExt = /\.(jpg|jpeg|png|webp|gif)$/i.test(baseUrl);
  if (hasExt) {
    return `${baseUrl}?name=orig`;
  }
  return `${baseUrl}?format=jpg&name=orig`;
}

/** 从 background-image CSS 提取 URL */
function extractBgImageUrl(bgImage: string): string | null {
  if (!bgImage) return null;
  // 匹配 url(...) 或 url("...")
  const match = bgImage.match(/url\(["']?([^"')]+)["']?\)/);
  return match?.[1] || null;
}

export function extractX(): ExtractResult | null {
  const url = window.location.href;
  if (!/\/status\/\d+/.test(url)) return null;

  // og:title 格式：(19) 4k arts & wallpapers on X: "Baby Riley is so cute https://t.co/xxx" / X
  // 提取引号内文本作为标题
  const ogTitle = meta("og:title") || "";
  let title = ogTitle;
  const titleMatch = ogTitle.match(/"([^"]+)"/);
  if (titleMatch) title = titleMatch[1];

  // author 从 URL 解析：x.com/{username}/status/{id}
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  const reservedPrefixes = [
    "i", "search", "home", "notifications", "explore",
    "settings", "messages", "compose", "hashtag", "topics",
  ];
  let author = "";
  if (
    pathParts.length >= 2 &&
    pathParts[1] === "status" &&
    !reservedPrefixes.includes(pathParts[0])
  ) {
    author = pathParts[0];
  }

  // og:image 是占位图（abs.twimg.com/rweb/ssr/default/v2/og/image.png），不用
  const thumbnail = "";

  // ★ 区域限定：只在主推文 article 内查找媒体
  const mainTweet = getMainTweet();
  const media_items: MediaItem[] = [];
  const seenUrls = new Set<string>();

  /** 添加媒体 URL（去重） */
  function addMedia(rawUrl: string, isVideo: boolean) {
    if (!rawUrl || !rawUrl.startsWith("http")) return;
    if (rawUrl.startsWith("blob:")) return;
    if (!rawUrl.includes("twimg.com")) return;
    const finalUrl = isVideo ? rawUrl : toOrigImageUrl(rawUrl);
    if (seenUrls.has(finalUrl)) return;
    seenUrls.add(finalUrl);
    media_items.push({ url: finalUrl, is_video: isVideo });
  }

  if (mainTweet) {
    // ── 视频 ──────────────────────────────────────────────
    // ★ X 视频用 HLS/MSE 流式加载，<video> 的 src 是 blob: 无法直接下载
    // 改为不提取视频直链，只发推文 URL，让 Lumio 后端用 yt-dlp 处理
    // （Lumio 的 XProvider 已支持 yt-dlp 下载 X 视频）

    // ── 图片策略 1：[data-testid="tweetPhoto"] 容器内的 img ──────
    // 这是 X 图片的标准容器，多图 carousel 每个图都在 tweetPhoto 里
    const tweetPhotoImgs = mainTweet.querySelectorAll(
      "[data-testid='tweetPhoto'] img",
    );
    for (const img of Array.from(tweetPhotoImgs)) {
      const src = img.getAttribute("src");
      if (src) addMedia(src, false);
    }

    // ── 图片策略 2：background-image 含 pbs.twimg.com/media/ ──────
    // 部分 carousel 用背景图
    const allElements = mainTweet.querySelectorAll("*");
    for (const el of Array.from(allElements)) {
      const bgImage = (el as HTMLElement).style?.backgroundImage;
      if (bgImage && bgImage.includes("pbs.twimg.com/media/")) {
        const bgUrl = extractBgImageUrl(bgImage);
        if (bgUrl) addMedia(bgUrl, false);
      }
    }

    // ── 图片策略 3：所有 img[src*='pbs.twimg.com/media/'] ──────
    // 兜底，确保不遗漏
    const allImgs = mainTweet.querySelectorAll("img[src*='pbs.twimg.com/media/']");
    for (const img of Array.from(allImgs)) {
      const src = img.getAttribute("src");
      if (src) addMedia(src, false);
    }
  }

  // 兜底：如果主推文没找到媒体，查全页 pbs.twimg.com/media/
  // （仅当主推文选择器失败时）
  if (media_items.length === 0) {
    const allMediaImgs = document.querySelectorAll("img[src*='pbs.twimg.com/media/']");
    for (const img of Array.from(allMediaImgs)) {
      const src = img.getAttribute("src");
      if (src) addMedia(src, false);
    }
  }

  // duration：从主推文首个 video 读取
  let duration: number | null = null;
  let videoPoster = "";
  if (mainTweet) {
    const firstVideo = mainTweet.querySelector("video");
    if (firstVideo?.duration && isFinite(firstVideo.duration)) {
      duration = Math.round(firstVideo.duration);
    }
    // ★ X 视频推文：用 video poster 作为 thumbnail（og:image 是占位图）
    if (firstVideo?.poster) {
      videoPoster = firstVideo.poster;
    }
  }

  // thumbnail 用第一张图，或视频 poster
  const finalThumb = media_items.find((m) => !m.is_video)?.url || videoPoster || thumbnail;

  // ★ X 视频推文：media_items 为空但有 video 元素
  // 不提取直链（blob: 无法下载），让 Lumio 后端用 yt-dlp 处理
  // direct_url 留空，Lumio 会走 GraphQL API / yt-dlp 路径

  return {
    url,
    title,
    author,
    thumbnail: finalThumb,
    platform: "x",
    media_items,
    duration,
    // 图片推文：direct_url 用第一张图
    // 视频推文：direct_url 留空，让 Lumio 后端处理
    direct_url: media_items.length > 0 ? media_items[0].url : "",
  };
}
