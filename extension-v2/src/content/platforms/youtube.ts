/**
 * YouTube 元数据提取
 * - 仅在 /watch 页提取详细数据
 * - ★ 等待 ytd-watch-metadata 渲染（SPA 路由切换时 og:title 可能短暂为分类标题如"电影和节目"）
 * - author 从 ytd-channel-name / ld+json 多路径兜底
 * - duration 从 ld+json 解析 PT#H#M#S
 * - ★ URL 规范化：只保留 v= 参数，移除所有跟踪参数（feature/si/pp/t 等），
 *   避免跟踪参数导致 yt-dlp 解析慢、触发限流、卡在合并中
 */
import { meta, parseDurationFromLd } from "../shared/og";
import type { ExtractResult } from "../shared/types";

/** 等待选择器出现（最多 maxWait ms） */
function waitForSelector(selector: string, maxWait = 3000, interval = 100): Promise<Element | null> {
  return new Promise((resolve) => {
    const start = Date.now();
    function check() {
      const el = document.querySelector(selector);
      if (el) {
        resolve(el);
        return;
      }
      if (Date.now() - start >= maxWait) {
        resolve(null);
        return;
      }
      setTimeout(check, interval);
    }
    check();
  });
}

/** 规范化 YouTube URL：只保留 v= 参数，移除所有跟踪参数
 *
 * 地址栏 URL 含大量跟踪参数（feature=share, si=..., pp=... 等），
 * 这些参数会让 yt-dlp 触发额外 token 验证导致解析慢、触发限流。
 * 分享按钮复制的是 youtu.be/ID?si=... 短链参数少所以快。
 */
function normalizeYouTubeUrl(rawUrl: string, videoId: string): string {
  if (videoId) {
    return `https://www.youtube.com/watch?v=${videoId}`;
  }
  return rawUrl;
}

export async function extractYouTube(): Promise<ExtractResult | null> {
  const rawUrl = window.location.href;
  if (!rawUrl.includes("/watch")) return null;

  const videoId = new URL(rawUrl).searchParams.get("v") || "";
  // ★ 规范化 URL：移除所有跟踪参数，只保留视频 ID
  // 避免含 feature=share/si=... 的 URL 传给 Lumio 后端 yt-dlp 解析慢
  const url = normalizeYouTubeUrl(rawUrl, videoId);

  // ★ 等待 ytd-watch-metadata 渲染（SPA 路由切换时可能短暂缺失）
  await waitForSelector("ytd-watch-metadata", 2500, 100);

  // 标题：优先从 ytd-watch-metadata 取，避免 og:title 返回分类标题
  const title =
    document
      .querySelector("ytd-watch-metadata h1 yt-formatted-string")
      ?.textContent?.trim() ||
    document.querySelector("h1.title yt-formatted-string")?.textContent?.trim() ||
    document.querySelector("h1.ytd-watch-metadata")?.textContent?.trim() ||
    // 兜底：og:title，但排除已知的分类标题
    (function () {
      const og = meta("og:title");
      // "电影和节目" 等 YouTube 通用标题说明 og:title 还没更新，不能用
      const genericTitles = ["电影和节目", "Movies and TV", "YouTube", "首页", "Home"];
      if (og && !genericTitles.includes(og)) return og;
      return "";
    })() ||
    document.title.replace(" - YouTube", "").trim();

  // author：多路径兜底
  const author =
    document
      .querySelector("ytd-watch-metadata ytd-channel-name yt-formatted-string a")
      ?.textContent?.trim() ||
    document
      .querySelector("ytd-channel-name yt-formatted-string a")
      ?.textContent?.trim() ||
    document.querySelector("link[itemprop='name']")?.getAttribute("content") ||
    meta("author") ||
    document
      .querySelector("span[itemprop='author'] link[itemprop='name']")
      ?.getAttribute("content") ||
    (function () {
      try {
        const ld = document.querySelector('script[type="application/ld+json"]');
        if (ld?.textContent) {
          const data = JSON.parse(ld.textContent);
          if (data?.author) {
            return Array.isArray(data.author)
              ? data.author[0]?.name
              : data.author?.name || "";
          }
        }
      } catch {
        /* ignore */
      }
      return "";
    })() ||
    "";

  // ★ 缩略图：og:image 经常被统一成 YouTube 通用图标，优先用 videoId 构造
  // i.ytimg.com/vi/{id}/hqdefault.jpg 是 YouTube 稳定的缩略图端点
  const ogImage = meta("og:image");
  const genericThumbs = [
    "yt/img/favicon",
    "yt_share",
    "youtube.com/img",
    "ggpht.com",
  ];
  const isGeneric = ogImage && genericThumbs.some((t) => ogImage.includes(t));
  const thumbnail =
    (ogImage && !isGeneric
      ? ogImage
      : "") ||
    (videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : "");

  const duration = parseDurationFromLd();

  return { url, title, author, thumbnail, duration, platform: "youtube" };
}
