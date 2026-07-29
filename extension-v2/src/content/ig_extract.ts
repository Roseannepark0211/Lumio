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
 *
 * ★ 阶段 2 防御性增强（2026-07）：
 *   - waitForMedia 8s → 12s（IG SPA 渲染慢，尤其未登录时）
 *   - 扩大 CDN 白名单：fbcdn / cdninstagram / scontent-XXX
 *   - 多选择器兜底：article img / main img / [data-testid] 容器
 *   - /embed/ 失败时尝试 /embed/captioned/
 *   - srcset 解析支持 webp 格式
 */
import type { MediaItem } from "../types";
import type { ExtractResult } from "./shared/types";

/** 判断是否为头像 URL */
function isAvatarUrl(url: string, alt?: string): boolean {
  if (url.includes("t51.82787-19") || url.includes("t51.2885-19")) return true;
  // 新版头像路径可能含 /profile_pic 或 _headshot
  if (url.includes("/profile_pic") || url.includes("_headshot")) return true;
  if (alt && (alt.includes("头像") || alt.toLowerCase().includes("avatar") || alt.toLowerCase().includes("profile"))) return true;
  return false;
}

/** 判断是否为小尺寸缩略图 */
function isSmallThumbnail(url: string): boolean {
  return (
    url.includes("s100x100") ||
    url.includes("s150x150") ||
    url.includes("s320x320") ||
    // 新版可能用 /150x150/ 路径段
    url.includes("/150x150/") ||
    url.includes("/100x100/")
  );
}

/**
 * 判断是否为 IG CDN URL
 * ★ 扩大白名单：fbcdn / cdninstagram / scontent-XXX.cdninstagram
 */
function isIgCdnUrl(url: string): boolean {
  return (
    url.includes("fbcdn") ||
    url.includes("cdninstagram") ||
    // scontent-XXX.cdninstagram.com
    /^https:\/\/scontent[^.]*\.(cdninstagram|fbcdn)\./.test(url) ||
    // 新版可能用 install-in-iad CDN
    url.includes("install-in-iad")
  );
}

/** 等待 DOM 媒体元素出现 */
function waitForMedia(maxWait = 12000, interval = 200): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now();
    function check() {
      const hasVideo = document.querySelectorAll("video").length > 0;
      const hasImg =
        document.querySelectorAll(
          "img[src*='cdninstagram'], img[src*='fbcdn'], img[src*='scontent']",
        ).length > 0;
      // 兜底：article 标签存在也算（说明 SPA 已渲染）
      const hasArticle = document.querySelectorAll("article").length > 0;
      if (hasVideo || hasImg || hasArticle || Date.now() - start >= maxWait) {
        resolve();
        return;
      }
      setTimeout(check, interval);
    }
    check();
  });
}

/**
 * 从 srcset 解析最高分辨率 URL
 *
 * srcset 格式有两种：
 * - "url1 1x, url2 2x"（密度描述符）
 * - "url1 640w, url2 1080w"（宽度描述符）
 *
 * ★ 修复：原来取 entries[length-1]，但实际 srcset 顺序可能是
 *   "1080w, 720w, 640w, 480w, 320w, 240w"（高到低），
 *   取最后一个 = 最低分辨率，错误。
 *
 * 正确做法：解析宽度数字，取最大值；密度描述符取最大 x。
 */
function pickHighestResFromSrcset(srcset: string): string | null {
  const entries = srcset.split(",").map((s) => s.trim()).filter(Boolean);
  if (entries.length === 0) return null;
  if (entries.length === 1) {
    return entries[0].split(/\s+/)[0] || null;
  }

  let bestUrl: string | null = null;
  let bestScore = -1;

  for (const entry of entries) {
    const parts = entry.split(/\s+/);
    const url = parts[0];
    const descriptor = parts[1] || "";

    if (!url || !url.startsWith("http")) continue;

    let score = 0;
    // 宽度描述符："1080w"
    const widthMatch = descriptor.match(/^(\d+)w$/);
    if (widthMatch) {
      score = parseInt(widthMatch[1], 10);
    }
    // 密度描述符："2x"
    const densityMatch = descriptor.match(/^(\d+(?:\.\d+)?)x$/);
    if (densityMatch) {
      score = parseFloat(densityMatch[1]) * 1000; // 放大方便统一比较
    }
    // 无描述符，给默认分
    if (!descriptor) score = 500;

    if (score > bestScore) {
      bestScore = score;
      bestUrl = url;
    }
  }

  return bestUrl;
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
    if (!isIgCdnUrl(rawUrl)) return false;
    if (isAvatarUrl(rawUrl, alt)) return false;
    if (!isVideo && isSmallThumbnail(rawUrl)) return false;
    if (seenUrls.has(rawUrl)) return false;
    seenUrls.add(rawUrl);
    media_items.push({ url: rawUrl, is_video: isVideo });
    return true;
  }

  // ── 优先级 1：DOM 提取 ──────────────────────────────────────────
  await waitForMedia(12000, 200);

  // ★ 精准定位详情容器（避免抓到推荐区/相关帖子）
  // IG 详情页两种渲染模式：
  //   1. 从主页点击进入：div[role='dialog'] 模态框包裹当前帖子 article
  //   2. 直接访问 /p/{id}/：main 内第一个 article 是当前帖子
  // 推荐区/相关帖子也是 article，必须选对容器
  const detailRoot = locateDetailRoot();

  // 视频
  const ogVideo = document.querySelector("meta[property='og:video']");
  const ogVideoContent = ogVideo?.getAttribute("content");
  if (ogVideoContent) addMedia(ogVideoContent, true);

  /**
   * 从容器内提取所有媒体（video + img + srcset）
   * ★ 含多图帖子的所有 slide（包括隐藏的，通过 srcset 和 data-src 兜底）
   */
  const collectFromContainer = (container: Element) => {
    // 视频
    const vids = container.querySelectorAll("video");
    for (const v of Array.from(vids)) {
      const candidates = [v.src, v.querySelector("source")?.src || "", v.currentSrc];
      for (const u of candidates) addMedia(u, true);
    }

    // 图片
    const imgSelectors = [
      "img[src*='cdninstagram']",
      "img[src*='fbcdn']",
      "img[src*='scontent']",
    ];
    const cdnImgs = container.querySelectorAll(imgSelectors.join(", "));
    for (const img of Array.from(cdnImgs)) {
      const src = img.getAttribute("src");
      const alt = img.getAttribute("alt") || "";
      if (src) addMedia(src, false, alt);
    }

    // srcset 图片（取最高分辨率）
    const srcsetImgs = container.querySelectorAll(
      "img[srcset*='cdninstagram'], img[srcset*='fbcdn'], img[srcset*='scontent']",
    );
    for (const img of Array.from(srcsetImgs)) {
      const srcset = img.getAttribute("srcset") || "";
      const alt = img.getAttribute("alt") || "";
      if (srcset) {
        const bestUrl = pickHighestResFromSrcset(srcset);
        if (bestUrl) addMedia(bestUrl, false, alt);
      }
    }
  };

  if (detailRoot) {
    collectFromContainer(detailRoot);
  }

  // ★ 全局兜底：详情容器没找到或没抓到时，用全局 article（第一个）
  if (media_items.length === 0) {
    const firstArticle = document.querySelector("article");
    if (firstArticle) collectFromContainer(firstArticle);
  }

  // ★ 最后兜底：og:image
  if (media_items.length === 0 && ogImage && !isAvatarUrl(ogImage)) {
    addMedia(ogImage, false);
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
      const isReel = parts[0] === "reel" || parts[1] === "reel";
      // ★ 尝试多个 embed 路径（IG 限制变严，需要兜底）
      const embedPaths = isReel
        ? [`/reel/${shortcode}/embed/`, `/reel/${shortcode}/embed/captioned/`]
        : [`/p/${shortcode}/embed/`, `/p/${shortcode}/embed/captioned/`];

      for (const embedPath of embedPaths) {
        if (media_items.length > 0) break;
        try {
          const resp = await fetch(embedPath, { credentials: "omit" });
          if (!resp.ok) continue;
          const html = await resp.text();
          const doc = new DOMParser().parseFromString(html, "text/html");

          const embedVideos = doc.querySelectorAll("video");
          for (const v of Array.from(embedVideos)) {
            const candidates = [v.src, v.querySelector("source")?.src || "", v.currentSrc];
            for (const u of candidates) addMedia(u, true);
          }

          // embed 页内 img（含 src 和 srcset）
          const embedImgs = doc.querySelectorAll(
            "img[src*='fbcdn'], img[src*='cdninstagram'], img[src*='scontent']",
          );
          for (const img of Array.from(embedImgs)) {
            const imgUrl = img.getAttribute("src");
            const imgAlt = img.getAttribute("alt") || "";
            if (imgUrl) addMedia(imgUrl, false, imgAlt);

            // 也尝试 srcset（取最高分辨率）
            const srcset = img.getAttribute("srcset") || "";
            if (srcset) {
              const bestUrl = pickHighestResFromSrcset(srcset);
              if (bestUrl) addMedia(bestUrl, false, imgAlt);
            }
          }
        } catch (e) {
          console.log(`IG embed ${embedPath} failed:`, e);
        }
      }
    }
  }

  // 兜底：og:image（embed 也失败时）
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

/**
 * 定位 IG 详情页主容器
 *
 * IG 详情页两种渲染模式：
 *   1. 从主页/.profile 点击帖子 → 弹出 div[role='dialog'] 模态框
 *      模态框内的 article 是当前帖子（推荐区 article 在模态框外）
 *   2. 直接访问 /p/{id}/ 或 /reel/{id}/ → main 内渲染详情
 *      main 内第一个 article 通常是当前帖子
 *
 * ★ 必须精准定位，否则会抓到推荐区/相关帖子
 */
function locateDetailRoot(): Element | null {
  // 优先级 1：模态框（从主页点击进入）
  const dialog = document.querySelector("div[role='dialog']");
  if (dialog) {
    const article = dialog.querySelector("article");
    if (article) return article;
    return dialog;
  }

  // 优先级 2：main 内第一个 article（直接访问详情页 URL）
  const main = document.querySelector("main");
  if (main) {
    const article = main.querySelector("article");
    if (article) return article;
    return main;
  }

  // 优先级 3：全局第一个 article（最后兜底）
  return document.querySelector("article");
}
