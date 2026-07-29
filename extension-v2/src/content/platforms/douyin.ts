/**
 * 抖音元数据提取
 *
 * ★ 策略：只提取元数据（标题/作者/缩略图），不提取 direct_url
 *   原因：抖音 <video>.src 是 blob: URL 无法下载；SSR 里的 play_addr 直链
 *   有 x-expires 签名时效（几小时），用户延迟下载会失效。
 *   发送帖子 URL 给 Lumio 后端，由 providers/douyin.py 调 aweme detail
 *   API 拿实时直链，更可靠。
 *
 * ★ 数据源优先级：
 *   1. RENDER_DATA（SSR 数据，<script id="RENDER_DATA">）
 *      - 视频详情页 (/video/{id}) 通常含 aweme.detail
 *      - ★ modal 模式 (/jingxuan?modal_id={id}) 只有 app key，不含 aweme.detail
 *   2. DOM fallback（[data-e2e='feed-active-video'] 容器 + 全局搜索）
 *   3. og 标签 + document.title 兜底
 *
 * ★ URL 规范化（关键）：
 *   后端 detector.py 只识别 /video/{id} 和 /note/{id}，不识别 modal_id 参数。
 *   modal 模式下必须把 URL 转换为标准 /video/{aweme_id} 再发给后端。
 *   aweme_id 来源优先级：
 *     1. [data-e2e='feed-active-video'] 的 data-e2e-vid 属性（最可靠）
 *     2. URL 的 modal_id 参数
 *     3. URL 路径 /video/{id} 或 /note/{id}
 *
 * ★ URL 格式（3 种）：
 *   - 视频详情页：https://www.douyin.com/video/{aweme_id}
 *   - 图文笔记页：https://www.douyin.com/note/{aweme_id}
 *   - ★ modal 模式：https://www.douyin.com/jingxuan?modal_id={aweme_id}
 *     或 https://www.douyin.com/jingxuan/search/{kw}?modal_id={aweme_id}
 *     （精选页/搜索页/关注页点视频弹出 modal）
 */
import { meta } from "../shared/og";
import type { ExtractResult } from "../shared/types";

/** RENDER_DATA 的最小类型定义（只关心我们用的字段） */
interface RenderData {
  [key: string]: {
    aweme?: {
      detail?: AwemeDetail | null;
    } | null;
  };
}

interface AwemeDetail {
  aweme_id?: string;
  desc?: string;
  create_time?: number;
  author?: {
    nickname?: string;
    sec_uid?: string;
  };
  video?: {
    cover?: { url_list?: string[] };
    origin_cover?: { url_list?: string[] };
    duration?: number;
  };
  image_post_info?: {
    images?: Array<{
      url_list?: string[];
    }>;
  } | null;
}

/**
 * 等待 DOM 元素出现（带超时重试）
 *
 * ★ 用途：抖音 modal 模式下，SPA 路由变化后 feed-active-video 可能还没渲染完
 *   需要等待该元素出现后再提取，否则会拿不到 data-e2e-vid 和作者信息
 *
 * @param selector CSS 选择器
 * @param maxAttempts 最大重试次数（每次间隔 200ms）
 * @returns 找到的元素或 null
 */
async function waitForElement(selector: string, maxAttempts = 5): Promise<Element | null> {
  for (let i = 0; i < maxAttempts; i++) {
    const el = document.querySelector(selector);
    if (el) return el;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return null;
}

/** 读取并解析 RENDER_DATA */
function readRenderData(): AwemeDetail | null {
  try {
    const script = document.querySelector("script#RENDER_DATA");
    if (!script?.textContent) return null;

    const decoded = decodeURIComponent(script.textContent);
    const data = JSON.parse(decoded) as RenderData;

    // 顶层 key 不固定（'43' / '44' / 'app' / 哈希），遍历找含 aweme.detail 的 key
    for (const key of Object.keys(data)) {
      const aweme = data[key]?.aweme;
      if (aweme?.detail) {
        return aweme.detail;
      }
    }
    return null;
  } catch {
    return null;
  }
}

/** 补全 URL 协议头（SSR 里的 URL 通常无协议头，如 //v26-web.douyinvod.com/...） */
function withProtocol(url: string): string {
  if (!url) return "";
  if (url.startsWith("//")) return "https:" + url;
  return url;
}

/**
 * 从 DOM 或 URL 提取 aweme_id
 *
 * ★ 优先级：
 *   1. [data-e2e='feed-active-video'] 的 data-e2e-vid 属性（最可靠，DOM 实时）
 *   2. URL 路径 /video/{id} 或 /note/{id}
 *   3. URL 参数 ?modal_id={id}
 */
function extractAwemeId(url: string): string | null {
  // 1. 从 DOM feed-active-video 元素的 data-e2e-vid 属性拿
  const feedEl = document.querySelector("[data-e2e='feed-active-video']");
  const vidFromDom = feedEl?.getAttribute("data-e2e-vid");
  if (vidFromDom) return vidFromDom;

  // 2. URL 路径 /video/{id} 或 /note/{id}
  const pathMatch = url.match(/\/(video|note)\/(\d+)/);
  if (pathMatch) return pathMatch[2];

  // 3. URL 参数 ?modal_id={id}
  const modalMatch = url.match(/[?&]modal_id=(\d+)/);
  if (modalMatch) return modalMatch[1];

  return null;
}

/**
 * 判断是否为图文笔记页
 *
 * ★ modal 模式下 URL 不含 /note/，需从 DOM 或 RENDER_DATA 判断
 */
function detectIsNote(url: string): boolean {
  // 1. URL 路径直接含 /note/
  if (/\/note\//.test(url)) return true;

  // 2. modal 模式下尝试从 RENDER_DATA 的 image_post_info 判断
  try {
    const script = document.querySelector("script#RENDER_DATA");
    if (script?.textContent) {
      const decoded = decodeURIComponent(script.textContent);
      const data = JSON.parse(decoded) as RenderData;
      for (const key of Object.keys(data)) {
        const detail = data[key]?.aweme?.detail;
        if (detail?.image_post_info?.images?.length) {
          return true;
        }
      }
    }
  } catch {
    // ignore
  }

  // 3. modal 模式下尝试从 DOM 判断（note-container 存在）
  if (document.querySelector("[data-e2e='note-container']")) return true;

  return false;
}

/**
 * DOM fallback：从全局 DOM 提取元数据
 *
 * ★ 关键修正（诊断数据验证）：
 *   - video-desc 和 author 元素不在 [data-e2e='feed-active-video'] 容器内！
 *   - 必须用 document.querySelector 全局搜索，不能限定在 feedContainer 内
 *   - [data-e2e='video-author-nickname'] 在 modal 模式下不存在（0 命中）
 *     需要多选择器 fallback
 *
 * ★ 作者名选择器优先级（modal 模式下需要）：
 *   1. [data-e2e='video-author-nickname']
 *   2. [data-e2e='author-nickname']
 *   3. a[data-e2e='video-author'] 的文本
 *   4. a[href*="/user/"] 的文本（作者主页链接，排除登录用户自己的链接）
 *   5. [class*='author'][class*='nickname'] 的文本
 */
function extractFromDom(isNote: boolean): ExtractResult | null {
  // ★ URL 规范化：modal 模式下转换为标准 /video/{id} 发给后端
  const originalUrl = window.location.href;
  const awemeId = extractAwemeId(originalUrl);
  const url = awemeId
    ? `https://www.douyin.com/${isNote ? "note" : "video"}/${awemeId}`
    : originalUrl;

  // 标题：[data-e2e='video-desc']（全局搜索，不在 feedContainer 内）
  let title = "";
  const descEl = document.querySelector("[data-e2e='video-desc']");
  if (descEl?.textContent) {
    title = descEl.textContent.trim();
  }
  if (!title) {
    const descAll = document.querySelectorAll("[data-e2e='video-desc']");
    if (descAll.length > 0) {
      title = (descAll[0].textContent || "").trim();
    }
  }
  if (!title) title = meta("og:title") || document.title.replace(/ - 抖音$/, "").trim();

  // 作者名：多选择器 fallback（全局搜索）
  // ★ 诊断数据验证：[data-e2e='feed-video-nickname'] 是真正的作者选择器
  //   textPreview: "@恬系"（count=2）
  let author = "";
  const authorSelectors = [
    "[data-e2e='feed-video-nickname']",
    "[data-e2e='video-author-nickname']",
    "[data-e2e='author-nickname']",
    "a[data-e2e='video-author']",
    "[class*='author'][class*='nickname']",
    "[class*='author-nickname']",
  ];
  for (const sel of authorSelectors) {
    try {
      const el = document.querySelector(sel);
      if (el?.textContent) {
        author = el.textContent.trim();
        if (author) break;
      }
    } catch {
      // 选择器语法错误，跳过
    }
  }
  // ★ 最后 fallback：a[href*="/user/"]（作者主页链接）
  // 注意排除登录用户自己的链接（通常在 sidebar/header）
  if (!author) {
    const userLinks = document.querySelectorAll("a[href*='/user/']");
    for (const link of Array.from(userLinks)) {
      // 排除 sidebar/header 内的链接（通常是登录用户自己）
      const closest = link.closest("[class*='sidebar'], [class*='header'], [class*='nav']");
      if (closest) continue;
      const text = (link.textContent || "").trim();
      if (text && text.length > 0 && text.length < 30) {
        author = text;
        break;
      }
    }
  }

  // 缩略图：优先 feed-active-video 内的 img，其次 video.poster，最后 og:image
  let thumbnail = "";
  const feedContainer = document.querySelector("[data-e2e='feed-active-video']");
  if (feedContainer) {
    // 容器内 douyinpic 图片（排除头像/avatar）
    const imgs = feedContainer.querySelectorAll("img[src*='douyinpic']");
    for (const img of Array.from(imgs)) {
      const src = img.getAttribute("src") || "";
      // 排除头像（aweme-avatar）
      if (src.includes("avatar") || src.includes("aweme-avatar")) continue;
      thumbnail = src;
      break;
    }
    // 如果容器内没找到，尝试 video.poster
    if (!thumbnail) {
      const video = feedContainer.querySelector("video");
      if (video?.poster) {
        thumbnail = video.poster;
      }
    }
  }
  // ★ 全局 fallback：找带 origin_cover 或 pcweb_cover 的图片
  if (!thumbnail) {
    const coverImgs = document.querySelectorAll("img[src*='douyinpic']");
    for (const img of Array.from(coverImgs)) {
      const src = img.getAttribute("src") || "";
      // 排除头像、avatar、100x100（头像尺寸）
      if (src.includes("avatar") || src.includes("aweme-avatar")) continue;
      if (src.includes("100x100") || src.includes("aweme-avatar")) continue;
      // 优先 origin_cover / pcweb_cover
      if (src.includes("origin_cover") || src.includes("pcweb_cover") || src.includes("image-cut")) {
        thumbnail = src;
        break;
      }
    }
    // 如果还没找到，取第一个非头像图片
    if (!thumbnail) {
      for (const img of Array.from(coverImgs)) {
        const src = img.getAttribute("src") || "";
        if (src.includes("avatar") || src.includes("aweme-avatar")) continue;
        if (src.includes("100x100")) continue;
        thumbnail = src;
        break;
      }
    }
  }
  if (!thumbnail) thumbnail = meta("og:image") || "";

  if (!title && !author && !thumbnail) {
    return null;
  }

  return {
    url,
    title,
    author,
    platform: "douyin",
    thumbnail,
    duration: null,
    type: isNote ? "image" : "video",
  };
}

export async function extractDouyin(): Promise<ExtractResult | null> {
  const originalUrl = window.location.href;
  const awemeId = extractAwemeId(originalUrl);
  if (!awemeId) return null;

  // ★ modal 模式下等待 feed-active-video 渲染完
  //   SPA 路由变化后 DOM 可能还没渲染，直接提取会拿不到 data-e2e-vid 和作者信息
  //   最多等待 1 秒（5 次 × 200ms），确保实时预览体验
  if (/[?&]modal_id=/.test(originalUrl)) {
    await waitForElement("[data-e2e='feed-active-video']", 5);
  }

  const isNote = detectIsNote(originalUrl);

  // ★ URL 规范化：modal 模式下转换为标准 /video/{id} 或 /note/{id} 发给后端
  // 后端 detector.py 只识别 /video/{id} 和 /note/{id}，不识别 modal_id 参数
  const url = `https://www.douyin.com/${isNote ? "note" : "video"}/${awemeId}`;

  // ── 优先级 1：RENDER_DATA ─────────────────────────────────────────
  // ★ modal 模式下 RENDER_DATA 通常不含 aweme.detail（只有 app key）
  //   此分支主要服务 /video/{id} 和 /note/{id} 详情页
  const detail = readRenderData();

  if (detail) {
    const title = detail.desc || meta("og:title") || document.title || "";
    const author = detail.author?.nickname || "";
    const duration = detail.video?.duration
      ? Math.floor(detail.video.duration / 1000)
      : null;

    // 缩略图：优先 origin_cover，其次 cover
    const thumbnail =
      withProtocol(detail.video?.origin_cover?.url_list?.[0] || "") ||
      withProtocol(detail.video?.cover?.url_list?.[0] || "") ||
      meta("og:image");

    // ★ modal 模式下，根据 image_post_info 修正 type
    const isActuallyNote = isNote || !!detail.image_post_info?.images?.length;

    return {
      url,
      title,
      author,
      platform: "douyin",
      thumbnail,
      duration,
      // 不设 direct_url / media_items：让后端 Provider 调 API 拿实时直链
      type: isActuallyNote ? "image" : "video",
    };
  }

  // ── 优先级 2：DOM fallback（RENDER_DATA 反爬 null 化或 modal 模式时）──
  const domResult = extractFromDom(isNote);
  if (domResult) {
    // ★ 确保 URL 是规范化后的（extractFromDom 内部也会规范化，这里双重保险）
    return { ...domResult, url };
  }

  // ── 优先级 3：og 标签 + document.title 兜底 ──
  const title =
    meta("og:title") ||
    document.title.replace(/ - 抖音$/, "").trim() ||
    `抖音${isNote ? "图文" : "视频"} ${awemeId}`;
  const author = meta("og:description") || "";
  const thumbnail = meta("og:image") || "";

  return {
    url,
    title,
    author,
    platform: "douyin",
    thumbnail,
    duration: null,
    type: isNote ? "image" : "video",
  };
}
