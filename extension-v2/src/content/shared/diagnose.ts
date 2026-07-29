/**
 * 诊断采集 — 一键采集当前页 DOM/State 元信息，导出 JSON 供离线分析
 *
 * 用途：小红书/IG/抖音等平台提取失败时，用户点 popup「诊断采集」按钮，
 * 自动采集当前页面的 URL/meta/选择器命中数/video/img/__INITIAL_STATE__ 片段，
 * 生成 JSON 下载到本地，贴给开发者定位根因。
 *
 * ★ 通用 + 平台特定两层采集：
 *   - 通用：所有平台都采集 meta/video/img/选择器命中数
 *   - 平台特定：小红书额外读 __INITIAL_STATE__.note.noteDetailMap 首个 entry
 *                （通过 background 中转到 MAIN world，绕过 CSP）
 */
import type { Platform } from "../../types";
import { detectPlatform } from "./detector";

/** 诊断报告 */
export interface DiagnoseReport {
  timestamp: string;
  url: string;
  platform: Platform;
  hostname: string;
  pathname: string;
  documentTitle: string;
  readyState: DocumentReadyState;
  meta: {
    ogTitle?: string;
    ogImage?: string;
    ogVideo?: string;
    ogDescription?: string;
    twitterCard?: string;
    twitterImage?: string;
    twitterTitle?: string;
  };
  /** 各选择器命中数（key=选择器表达式，value=数量） */
  selectors: Record<string, number>;
  /** 前 N 个 video 元素的关键属性 */
  videos: Array<{
    src: string;
    currentSrc: string;
    poster: string;
    sources: string[];
    parentClassName: string;
  }>;
  /** 前 N 个 img 元素的关键属性 */
  images: Array<{
    src: string;
    srcset: string;
    alt: string;
    className: string;
    parentClassName: string;
  }>;
  /** __INITIAL_STATE__ 关键片段（仅小红书等有此结构的平台） */
  initialState?: unknown;
  /** 媒体容器 DOM 结构（小红书专用，诊断当前帖子媒体渲染方式） */
  mediaContainerDom?: {
    outerHtmlPreview: string;
    childElements: Array<{
      tag: string;
      className: string;
      src?: string;
      srcset?: string;
      bgImage?: string;
      dataSrc?: string;
      poster?: string;
      childCount: number;
    }>;
  };
  /** 采集过程中的备注/警告 */
  notes: string[];
}

/** 通用选择器清单（跨平台） */
const COMMON_SELECTORS: string[] = [
  "video",
  "img",
  "source",
  "meta[property='og:image']",
  "meta[property='og:video']",
  "meta[property='og:title']",
  "meta[name='twitter:image']",
];

/** 小红书专用选择器 */
const XHS_SELECTORS: string[] = [
  "img[src*='xhscdn']",
  "img[src*='sns-img']",
  "img[src*='xhscdn']",
  ".media-container",
  ".swiper",
  "[class*='note']",
  "[class*='container']",
];

/** Instagram 专用选择器 */
const IG_SELECTORS: string[] = [
  "img[src*='cdninstagram']",
  "img[src*='fbcdn']",
  "img[srcset*='cdninstagram']",
  "img[srcset*='fbcdn']",
  "article",
  "[data-testid]",
  "video[src*='cdninstagram']",
  "video[src*='fbcdn']",
];

/** 抖音专用选择器 */
const DOUYIN_SELECTORS: string[] = [
  "video",
  "xg-video",
  "xgplayer",
  "[class*='video']",
  "[class*='player']",
  "[data-e2e]",
  "img[src*='douyinpic']",
  "img[src*='bytecdn']",
];

/** 限制采集数量，避免 JSON 过大 */
const MAX_VIDEOS = 20;
const MAX_IMAGES = 30;

/** 读 meta 标签 content */
function meta(attr: "property" | "name", key: string): string | undefined {
  const el = document.querySelector(`meta[${attr}='${key}']`);
  const v = el?.getAttribute("content") || undefined;
  return v && v.trim() ? v : undefined;
}

/** 计算选择器命中数 */
function countSelector(selector: string): number {
  try {
    return document.querySelectorAll(selector).length;
  } catch {
    return -1; // 选择器语法错误
  }
}

/** 采集 video 元素 */
function collectVideos(): DiagnoseReport["videos"] {
  const out: DiagnoseReport["videos"] = [];
  const vids = document.querySelectorAll("video");
  for (let i = 0; i < Math.min(vids.length, MAX_VIDEOS); i++) {
    const v = vids[i];
    const sources: string[] = [];
    v.querySelectorAll("source").forEach((s) => {
      const src = s.getAttribute("src");
      if (src) sources.push(src);
    });
    out.push({
      src: v.src || "",
      currentSrc: v.currentSrc || "",
      poster: v.poster || "",
      sources,
      parentClassName: v.parentElement?.className || "",
    });
  }
  return out;
}

/** 采集 img 元素（过滤明显无关的图标/头像） */
function collectImages(): DiagnoseReport["images"] {
  const out: DiagnoseReport["images"] = [];
  const imgs = document.querySelectorAll("img");
  for (let i = 0; i < Math.min(imgs.length, MAX_IMAGES); i++) {
    const img = imgs[i];
    const src = img.getAttribute("src") || "";
    // 跳过纯 data: 图标
    if (src.startsWith("data:image/svg") || src.startsWith("data:image/gif")) continue;
    out.push({
      src,
      srcset: img.getAttribute("srcset") || "",
      alt: img.getAttribute("alt") || "",
      className: img.className || "",
      parentClassName: img.parentElement?.className || "",
    });
  }
  return out;
}

/** 采集 .media-container 内的 DOM 结构（小红书专用，诊断当前帖子媒体渲染方式） */
function collectMediaContainerDom(): {
  outerHtmlPreview: string;
  childElements: Array<{
    tag: string;
    className: string;
    src?: string;
    srcset?: string;
    bgImage?: string;
    dataSrc?: string;
    poster?: string;
    childCount: number;
  }>;
} {
  const container =
    document.querySelector(".media-container") ||
    document.querySelector("[class*='note-detail']") ||
    document.querySelector(".note-container");
  if (!container) {
    return { outerHtmlPreview: "(未找到媒体容器)", childElements: [] };
  }

  // outerHTML 前 3000 字符
  const outerHtmlPreview = container.outerHTML.slice(0, 3000);

  // 采集容器内所有子元素（递归 2 层）
  const childElements: Array<{
    tag: string;
    className: string;
    src?: string;
    srcset?: string;
    bgImage?: string;
    dataSrc?: string;
    poster?: string;
    childCount: number;
  }> = [];
  const walk = (el: Element, depth: number) => {
    if (depth > 3) return;
    for (let i = 0; i < Math.min(el.children.length, 30); i++) {
      const child = el.children[i];
      const style = window.getComputedStyle(child);
      const bgImage = style.backgroundImage;
      childElements.push({
        tag: child.tagName.toLowerCase(),
        className: child.className || "",
        src: child.getAttribute("src") || undefined,
        srcset: child.getAttribute("srcset") || undefined,
        bgImage:
          bgImage && bgImage !== "none"
            ? bgImage.slice(0, 500)
            : undefined,
        dataSrc: child.getAttribute("data-src") || undefined,
        poster: child.getAttribute("poster") || undefined,
        childCount: child.children.length,
      });
      walk(child, depth + 1);
    }
  };
  walk(container, 0);

  return { outerHtmlPreview, childElements };
}

/**
 * 通过 background 中转读取 __INITIAL_STATE__（小红书专用，绕过 CSP）
 * 复用 xhs-read-state 通道
 */
function readInitialStateViaBg(timeout = 3000): Promise<unknown> {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage({ type: "xhs-read-state" }, (state) => {
        if (chrome.runtime.lastError) {
          resolve({ __error: chrome.runtime.lastError.message });
          return;
        }
        resolve(state || null);
      });
      setTimeout(() => resolve({ __error: "timeout" }), timeout);
    } catch (e) {
      resolve({ __error: String(e) });
    }
  });
}

/**
 * 裁剪小红书 __INITIAL_STATE__，只保留 noteDetailMap 首个 entry
 * 避免推荐列表导致 JSON 过大
 */
function trimXhsState(state: unknown): unknown {
  if (!state || typeof state !== "object") return state;
  try {
    const s = state as {
      note?: {
        noteDetailMap?: Record<string, unknown>;
        noteMap?: Record<string, unknown>;
      };
    };
    const map = s.note?.noteDetailMap || s.note?.noteMap;
    if (!map) return { __note_map_missing: true, topKeys: Object.keys(s) };
    const keys = Object.keys(map);
    if (keys.length === 0) return { __note_map_empty: true };
    // 只取第一个 entry
    return {
      noteDetailMapKeys: keys,
      firstEntry: map[keys[0]],
      topLevelKeys: Object.keys(s),
    };
  } catch (e) {
    return { __trim_error: String(e) };
  }
}

/**
 * 主采集函数
 */
export async function diagnose(): Promise<DiagnoseReport> {
  console.log("[Lumio-diag] diagnose() 开始");
  const platform = detectPlatform();
  const url = window.location.href;
  const notes: string[] = [];
  console.log("[Lumio-diag] platform=", platform, "url=", url);

  // 1. 通用选择器 + 平台特定选择器
  const platformSelectors =
    platform === "xiaohongshu"
      ? XHS_SELECTORS
      : platform === "instagram"
        ? IG_SELECTORS
        : platform === "youtube" || platform === "bilibili" || platform === "x" || platform === "kuaishou"
          ? []
          : DOUYIN_SELECTORS; // 未识别平台按抖音选择器试一遍（兜底）

  const selectors: Record<string, number> = {};
  for (const sel of [...COMMON_SELECTORS, ...platformSelectors]) {
    if (selectors[sel] === undefined) {
      selectors[sel] = countSelector(sel);
    }
  }
  console.log("[Lumio-diag] selectors 完成", selectors);

  // 2. meta 标签
  const metaInfo = {
    ogTitle: meta("property", "og:title"),
    ogImage: meta("property", "og:image"),
    ogVideo: meta("property", "og:video"),
    ogDescription: meta("property", "og:description"),
    twitterCard: meta("name", "twitter:card"),
    twitterImage: meta("name", "twitter:image"),
    twitterTitle: meta("name", "twitter:title"),
  };

  // 3. video / img 元素
  const videos = collectVideos();
  const images = collectImages();
  console.log("[Lumio-diag] videos=", videos.length, "images=", images.length);

  // 4. 平台特定：小红书 __INITIAL_STATE__
  let initialState: unknown;
  if (platform === "xiaohongshu") {
    notes.push("小红书：通过 background 读取 __INITIAL_STATE__");
    console.log("[Lumio-diag] 读取 __INITIAL_STATE__...");
    const raw = await readInitialStateViaBg(3000);
    console.log("[Lumio-diag] __INITIAL_STATE__ 返回", typeof raw, raw ? "有数据" : "空");
    initialState = trimXhsState(raw);
    if (!raw) {
      notes.push("⚠️ __INITIAL_STATE__ 读取失败（可能 CSP 拦截或 background 异常）");
    } else if (raw && typeof raw === "object" && (raw as { __error?: string }).__error) {
      notes.push(`⚠️ __INITIAL_STATE__ 读取异常: ${(raw as { __error: string }).__error}`);
    }
  }

  // 6. 平台特定：小红书媒体容器 DOM 结构（诊断当前帖子媒体渲染方式）
  let mediaContainerDom: DiagnoseReport["mediaContainerDom"];
  if (platform === "xiaohongshu") {
    mediaContainerDom = collectMediaContainerDom();
    console.log("[Lumio-diag] mediaContainerDom 子元素数:", mediaContainerDom.childElements.length);
  }

  // 7. 备注：检测明显的提取失败特征
  if (platform === "xiaohongshu") {
    if (selectors["img[src*='xhscdn']"] === 0 && selectors["img[src*='sns-img']"] === 0) {
      notes.push("⚠️ 小红书 CDN 图片选择器全部 0 命中，可能 DOM 改版");
    }
    if (videos.length > 0 && videos.every((v) => v.src.startsWith("blob:"))) {
      notes.push("⚠️ video 全为 blob: URL，__INITIAL_STATE__ 提取是唯一路径");
    }
  }
  if (platform === "instagram") {
    if (selectors["img[src*='cdninstagram']"] === 0 && selectors["img[src*='fbcdn']"] === 0) {
      notes.push("⚠️ IG CDN 选择器全部 0 命中，可能 DOM 改版或未登录");
    }
  }

  console.log("[Lumio-diag] diagnose() 完成");
  return {
    timestamp: new Date().toISOString(),
    url,
    platform,
    hostname: window.location.hostname,
    pathname: window.location.pathname,
    documentTitle: document.title,
    readyState: document.readyState,
    meta: metaInfo,
    selectors,
    videos,
    images,
    initialState,
    mediaContainerDom,
    notes,
  };
}
