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
  /** RENDER_DATA 关键片段（仅抖音，URL 编码的 SSR JSON） */
  renderData?: unknown;
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
  /** 抖音专用：视频/图文笔记容器 DOM 结构（诊断 RENDER_DATA 失效时的 DOM fallback） */
  douyinMediaDom?: {
    pageType: "video" | "note" | "unknown";
    /** 找到的容器选择器（用于追溯命中了哪条规则） */
    matchedSelector: string;
    outerHtmlPreview: string;
    childElements: Array<{
      tag: string;
      className: string;
      src?: string;
      poster?: string;
      dataSrc?: string;
      dataE2e?: string;
      bgImage?: string;
      childCount: number;
    }>;
  };
  /** 抖音专用：xgplayer 西瓜播放器元素信息 */
  douyinPlayer?: {
    found: boolean;
    /** 找到的播放器元素标签名（xgplayer / xg-video / video 等） */
    tag: string;
    className: string;
    /** video 元素属性 */
    videoSrc: string;
    videoCurrentSrc: string;
    videoPoster: string;
    /** xgplayer 内部 <video> 子元素数量 */
    childVideoCount: number;
    /** xgplayer 配置（window 上挂载的实例信息，可能为空） */
    playerState?: string;
  };
  /** 抖音专用：所有 [data-e2e] 元素的值列表（便于定位作者/标题等元素的真实选择器） */
  douyinDataE2eValues?: Array<{
    value: string;
    count: number;
    /** 第一个匹配元素的标签名和 class（便于定位） */
    firstMatch: {
      tag: string;
      className: string;
      textPreview: string;
    };
  }>;
  /** 微博专用：媒体容器 DOM 结构（诊断 SSR __INITIAL_STATE__ 失效时的 DOM fallback） */
  weiboMediaDom?: {
    pageType: "video" | "image" | "livephoto" | "unknown";
    /** 找到的容器选择器（用于追溯命中了哪条规则） */
    matchedSelector: string;
    outerHtmlPreview: string;
    childElements: Array<{
      tag: string;
      className: string;
      src?: string;
      poster?: string;
      dataSrc?: string;
      bgImage?: string;
      href?: string;
      childCount: number;
    }>;
  };
  /** 微博专用：__INITIAL_STATE__ 关键片段（weibo.com PC 版有此结构） */
  weiboInitialState?: unknown;
  /** 微博专用：$render_data 片段（m.weibo.cn 移动版有时用此结构） */
  weiboRenderData?: unknown;
  /** 微博专用：帖子列表结构（博主主页流式列表，每个帖子的容器链 + outerHTML 预览） */
  weiboPosts?: {
    /** 找到的帖子总数 */
    postCount: number;
    /** 采样的帖子（最多 3 个，避免 JSON 过大） */
    samples: Array<{
      /** 帖子正文文本（来自 .wbtext） */
      text: string;
      /** 帖子正文元素的 class */
      textClassName: string;
      /** 从正文向上 5 层的祖先链（tag + class，用于定位帖子完整容器） */
      ancestorChain: Array<{
        tag: string;
        className: string;
        /** 该祖先的子元素数量（帮助判断是否是帖子容器） */
        childCount: number;
        /** 该祖先内是否含 video 元素 */
        hasVideo: boolean;
        /** 该祖先内是否含 sinaimg 图片 */
        hasSinaimg: boolean;
        /** 该祖先内是否含 a[href*='/u/']（作者链接） */
        hasAuthorLink: boolean;
      }>;
      /** 推测的帖子完整容器 outerHTML 预览（限 3000 字符） */
      postContainerPreview?: string;
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
  // ★ xgplayer 是 class 名不是 tag（诊断数据验证），用 class 选择器
  "video[class*='xgplayer']",
  "video[class*='xg-video']",
  "[class*='xg-video-container']",
  "[class*='xgplayer']",
  "[class*='video']",
  "[class*='player']",
  "[data-e2e]",
  "img[src*='douyinpic']",
  "img[src*='bytecdn']",
  // 视频详情页容器（视频+信息）
  "[data-e2e='scroll-list']",
  "[data-e2e='feed-active-video']",
  "[data-e2e='video-desc']",
  "[data-e2e='video-author-nickname']",
  // 图文笔记页容器
  "[data-e2e='note-container']",
  "[data-e2e='note-slider']",
  "[class*='note']",
  "[class*='slider']",
  "[class*='swiper']",
  // 抖音 SSR 数据 script
  "script#RENDER_DATA",
  // __INITIAL_STATE__ 兜底（抖音某些页面也有）
  "script#INITIAL_STATE",
  // __NEXT_DATA__ 兜底（部分页面 Next.js 同构）
  "script#__NEXT_DATA__",
];

/** 微博专用选择器 */
const WEIBO_SELECTORS: string[] = [
  // 视频/图片元素
  "video",
  "video[src]",
  "video[poster]",
  "img[src*='sinaimg']",
  "img[src*='sinaimg.cn']",
  "img[src*='sinacn']",
  "source[src*='sinaimg']",
  // m.weibo.cn 移动版容器
  ".weibo-text",
  ".weibo-top",
  "[class*='weibo-text']",
  "[class*='feed_list_content']",
  "[class*='wbtext']",
  // weibo.com PC 版容器
  "[node-type='feed_list_content']",
  "[node-type='feed_list_author']",
  "[class*='detail_wbtext']",
  "[class*='detail_username']",
  "[class*='username']",
  "[class*='author'][class*='name']",
  // 媒体容器
  "[class*='detail']",
  "[class*='media-wrap']",
  "[class*='pic_list']",
  "[class*='wbv-play']",
  "[class*='video']",
  "[class*='player']",
  // 作者链接
  "a[href*='/u/']",
  "a[href*='/profile/']",
  // SSR 数据 script
  "script#__INITIAL_STATE__",
  "script#__NEXT_DATA__",
  "script[type='application/json']",
  // og 标签（部分页面有）
  "meta[property='og:title']",
  "meta[property='og:image']",
  "meta[property='og:video']",
  "meta[property='og:url']",
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

/**
 * 从指定容器内采集 video 元素（抖音聚焦策略，避免推荐页数据冗余）
 * 如果容器不存在，返回空数组
 */
function collectVideosFromContainer(containerSelector: string): DiagnoseReport["videos"] {
  const out: DiagnoseReport["videos"] = [];
  const container = document.querySelector(containerSelector);
  if (!container) return out;
  const vids = container.querySelectorAll("video");
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

/**
 * 从指定容器内采集 img 元素（抖音聚焦策略，避免推荐页封面/图标数据冗余）
 * 如果容器不存在，返回空数组
 */
function collectImagesFromContainer(containerSelector: string): DiagnoseReport["images"] {
  const out: DiagnoseReport["images"] = [];
  const container = document.querySelector(containerSelector);
  if (!container) return out;
  const imgs = container.querySelectorAll("img");
  for (let i = 0; i < Math.min(imgs.length, MAX_IMAGES); i++) {
    const img = imgs[i];
    const src = img.getAttribute("src") || "";
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
 * 抖音专用：采集视频/图文笔记容器 DOM 结构
 *
 * ★ 抖音 DOM 与小红书/IG 差异：
 *   - 视频详情页 (/video/{id})：用 [data-e2e="scroll-list"] 包裹整个 feed，
 *     当前激活的视频在 [data-e2e="feed-active-video"] 内
 *   - ★ modal 模式 (/jingxuan?modal_id={id})：同样用 [data-e2e="feed-active-video"]
 *     标记当前激活视频，但不在 scroll-list 内
 *   - 图文笔记页 (/note/{id})：图片在 swiper/slider 容器内，但选择器
 *     与小红书完全不同（抖音用 [data-e2e="note-container"]）
 *   - 视频播放器是 xgplayer（★ 是 class 名，不是自定义元素 <xgplayer>）
 *
 * ★ 采集策略：按优先级尝试多个选择器，找到第一个非空容器即采集
 *   ★ 关键修正：[data-e2e='feed-active-video'] 在所有视频页（含 modal）都优先尝试
 */
function collectDouyinMediaDom(): {
  pageType: "video" | "note" | "unknown";
  matchedSelector: string;
  outerHtmlPreview: string;
  childElements: Array<{
    tag: string;
    className: string;
    src?: string;
    poster?: string;
    dataSrc?: string;
    dataE2e?: string;
    bgImage?: string;
    childCount: number;
  }>;
} {
  const url = window.location.href;
  // ★ pageType 判断：含 modal_id 的也算 video（modal 模式）
  const pageType: "video" | "note" | "unknown" = /\/video\//.test(url) || /[?&]modal_id=/.test(url)
    ? "video"
    : /\/note\//.test(url)
      ? "note"
      : "unknown";

  // ★ 抖音容器选择器优先级（从精准到宽泛）
  // ★ 关键修正：
  //   1. [data-e2e='feed-active-video'] 在所有视频页（含 modal）都优先尝试
  //   2. xgplayer 是 class 名不是 tag，用 [class*='xgplayer'] 而非 <xgplayer>
  //   3. unknown pageType 也尝试 feed-active-video（用户可能在其他页面点了视频）
  const candidateSelectors =
    pageType === "note"
      ? [
          "[data-e2e='note-container']",
          "[data-e2e='note-slider']",
          "[class*='note'][class*='container']",
          "[class*='swiper']",
          "[class*='slider']",
        ]
      : [
          // 视频页 + modal 模式 + unknown 都走这套
          "[data-e2e='feed-active-video']",
          "[data-e2e='scroll-list'] [data-e2e='feed-active-video']",
          "[data-e2e='scroll-list']",
          "[class*='xg-video-container']",
          "[class*='xgplayer']",
          "[class*='player'][class*='container']",
        ];

  let container: Element | null = null;
  let matchedSelector = "";
  for (const sel of candidateSelectors) {
    try {
      const el = document.querySelector(sel);
      if (el) {
        container = el;
        matchedSelector = sel;
        break;
      }
    } catch {
      // 选择器语法错误，跳过
    }
  }

  if (!container) {
    return {
      pageType,
      matchedSelector: "",
      outerHtmlPreview: "(未找到抖音媒体容器)",
      childElements: [],
    };
  }

  // outerHTML 前 3000 字符
  const outerHtmlPreview = container.outerHTML.slice(0, 3000);

  // 采集容器内所有子元素（递归 3 层，最多 40 个/层）
  const childElements: Array<{
    tag: string;
    className: string;
    src?: string;
    poster?: string;
    dataSrc?: string;
    dataE2e?: string;
    bgImage?: string;
    childCount: number;
  }> = [];
  const walk = (el: Element, depth: number) => {
    if (depth > 3) return;
    for (let i = 0; i < Math.min(el.children.length, 40); i++) {
      const child = el.children[i];
      const style = window.getComputedStyle(child);
      const bgImage = style.backgroundImage;
      childElements.push({
        tag: child.tagName.toLowerCase(),
        className: child.className || "",
        src: child.getAttribute("src") || undefined,
        poster: child.getAttribute("poster") || undefined,
        dataSrc: child.getAttribute("data-src") || undefined,
        dataE2e: child.getAttribute("data-e2e") || undefined,
        bgImage:
          bgImage && bgImage !== "none"
            ? bgImage.slice(0, 500)
            : undefined,
        childCount: child.children.length,
      });
      walk(child, depth + 1);
    }
  };
  walk(container, 0);

  return { pageType, matchedSelector, outerHtmlPreview, childElements };
}

/**
 * 抖音专用：采集 xgplayer 西瓜播放器元素信息
 *
 * ★ 关键修正：xgplayer 是 class 名（xg-video-container xgplayer-sr），
 *   不是自定义元素 <xgplayer>！诊断数据显示 document.querySelector("xgplayer") 返回 null。
 *   实际播放器是 <video class="xg-video-container xgplayer-sr"> 或
 *   <div class="xg-video-container"><video>...</video></div>
 *
 * ★ 采集目的：定位播放器容器结构，为 DOM fallback 提取做准备
 *   （RENDER_DATA 反爬 null 化时，可能需要从 DOM 拿 poster 当缩略图）
 */
function collectDouyinPlayer(): {
  found: boolean;
  tag: string;
  className: string;
  videoSrc: string;
  videoCurrentSrc: string;
  videoPoster: string;
  childVideoCount: number;
  playerState?: string;
} {
  // ★ 优先级：[data-e2e='feed-active-video'] 内的 video > [class*='xgplayer'] > [class*='xg-video'] > video
  // feed-active-video 内的 video 是当前激活视频，最准确
  const candidates = [
    "[data-e2e='feed-active-video'] video",
    "video[class*='xgplayer']",
    "video[class*='xg-video']",
    "[class*='xg-video-container'] video",
    "[class*='xgplayer'] video",
    "video",
  ];
  for (const sel of candidates) {
    try {
      const el = document.querySelector(sel) as HTMLVideoElement | null;
      if (el) {
        // 找父容器的 class（含 xgplayer 信息）
        const parent = el.parentElement;
        const parentClass = parent?.className || "";
        return {
          found: true,
          tag: "video",
          className: el.className || parentClass,
          videoSrc: el.src || "",
          videoCurrentSrc: el.currentSrc || "",
          videoPoster: el.poster || "",
          childVideoCount: 1,
        };
      }
    } catch {
      // 选择器语法错误，跳过
    }
  }
  return {
    found: false,
    tag: "",
    className: "",
    videoSrc: "",
    videoCurrentSrc: "",
    videoPoster: "",
    childVideoCount: 0,
  };
}

/**
 * 微博专用：采集媒体容器 DOM 结构
 *
 * ★ 微博 DOM 结构差异（待诊断数据确认）：
 *   - m.weibo.cn 移动版：用 .weibo-text 包正文，.weibo-top 包作者，img/video 散在 .media 区域
 *   - weibo.com PC 版：用 [node-type='feed_list_content'] 包正文，
 *     [class*='detail_wbtext'] / [class*='detail_username'] 包详细元素
 *   - 视频帖子：含 <video> 元素（src 是 blob:）
 *   - 图片帖子：含多个 img[src*='sinaimg']（large/thumb 等尺寸后缀）
 *   - livephoto：同时含图片和视频
 *
 * ★ 采集策略：按优先级尝试多个选择器，找到第一个非空容器即采集
 *   严格限定在主贴区域，避免抓到推荐区/评论区
 */
function collectWeiboMediaDom(): {
  pageType: "video" | "image" | "livephoto" | "unknown";
  matchedSelector: string;
  outerHtmlPreview: string;
  childElements: Array<{
    tag: string;
    className: string;
    src?: string;
    poster?: string;
    dataSrc?: string;
    bgImage?: string;
    href?: string;
    childCount: number;
  }>;
} {
  // 先粗略判断 pageType（DOM 实际渲染后再修正）
  const hasVideo = document.querySelectorAll("video").length > 0;
  const hasImage = document.querySelectorAll("img[src*='sinaimg']").length > 0;
  const ogVideo = meta("property", "og:video");
  const pageType: "video" | "image" | "livephoto" | "unknown" =
    (hasVideo || ogVideo) && hasImage
      ? "livephoto"
      : hasVideo || ogVideo
        ? "video"
        : hasImage
          ? "image"
          : "unknown";

  // ★ 微博容器选择器优先级（从精准到宽泛）
  // 不同页面（PC 版 / 移动版 / 详情页 / 详情 ID）DOM 结构差异较大
  const candidateSelectors = [
    // weibo.com PC 版详情页
    "[class*='detail_wbtext']",
    "[class*='detail_username']",
    "[node-type='feed_list_content']",
    "[node-type='feed_list_author']",
    // m.weibo.cn 移动版
    ".weibo-text",
    ".weibo-top",
    "[class*='weibo-text']",
    "[class*='feed_list_content']",
    "[class*='wbtext']",
    // 通用媒体容器
    "[class*='media-wrap']",
    "[class*='pic_list']",
    "[class*='wbv-play']",
    "[class*='detail']",
  ];

  let container: Element | null = null;
  let matchedSelector = "";
  for (const sel of candidateSelectors) {
    try {
      const el = document.querySelector(sel);
      if (el) {
        container = el;
        matchedSelector = sel;
        break;
      }
    } catch {
      // 选择器语法错误，跳过
    }
  }

  if (!container) {
    return {
      pageType,
      matchedSelector: "",
      outerHtmlPreview: "(未找到微博媒体容器)",
      childElements: [],
    };
  }

  // outerHTML 前 3000 字符
  const outerHtmlPreview = container.outerHTML.slice(0, 3000);

  // 采集容器内所有子元素（递归 3 层，最多 40 个/层）
  const childElements: Array<{
    tag: string;
    className: string;
    src?: string;
    poster?: string;
    dataSrc?: string;
    bgImage?: string;
    href?: string;
    childCount: number;
  }> = [];
  const walk = (el: Element, depth: number) => {
    if (depth > 3) return;
    for (let i = 0; i < Math.min(el.children.length, 40); i++) {
      const child = el.children[i];
      const style = window.getComputedStyle(child);
      const bgImage = style.backgroundImage;
      childElements.push({
        tag: child.tagName.toLowerCase(),
        className: child.className || "",
        src: child.getAttribute("src") || undefined,
        poster: child.getAttribute("poster") || undefined,
        dataSrc: child.getAttribute("data-src") || undefined,
        bgImage:
          bgImage && bgImage !== "none"
            ? bgImage.slice(0, 500)
            : undefined,
        href: child.getAttribute("href") || undefined,
        childCount: child.children.length,
      });
      walk(child, depth + 1);
    }
  };
  walk(container, 0);

  return { pageType, matchedSelector, outerHtmlPreview, childElements };
}

/**
 * 微博专用：采集帖子列表结构
 *
 * ★ 微博博主主页是流式列表，多个帖子在同一页面：
 *   - 每个帖子正文用 [class*='wbtext'] 包裹
 *   - 帖子完整容器（含作者+正文+媒体）的 class 未知，需通过 .wbtext 向上找
 *
 * ★ 采集策略：
 *   1. 找所有 [class*='wbtext'] 元素（每个对应一个帖子正文）
 *   2. 对前 3 个帖子，从 .wbtext 向上遍历 5 层祖先
 *   3. 每层祖先记录 tag + class + 子元素数 + 是否含 video/sinaimg/作者链接
 *   4. 推测"帖子完整容器"：第一个同时含正文+媒体+作者链接的祖先
 *
 * ★ 输出用于：
 *   - 确认帖子容器的 class 模式（用于 weibo.ts extractFromDom）
 *   - 确认帖子内的媒体结构（video/img 在帖子内的位置）
 */
function collectWeiboPosts(): DiagnoseReport["weiboPosts"] {
  const wbtextEls = document.querySelectorAll("[class*='wbtext']");
  if (wbtextEls.length === 0) {
    return { postCount: 0, samples: [] };
  }

  const samples: NonNullable<NonNullable<DiagnoseReport["weiboPosts"]>["samples"]> = [];
  const maxSamples = Math.min(wbtextEls.length, 3);

  for (let i = 0; i < maxSamples; i++) {
    const wbtext = wbtextEls[i] as HTMLElement;
    const text = (wbtext.textContent || "").trim().slice(0, 200);
    const textClassName = wbtext.className || "";

    // 向上遍历 5 层祖先
    const ancestorChain: NonNullable<NonNullable<NonNullable<DiagnoseReport["weiboPosts"]>["samples"][number]>["ancestorChain"][number]>[] = [];
    let current: Element | null = wbtext.parentElement;
    let postContainer: Element | null = null;

    for (let depth = 0; depth < 5 && current; depth++) {
      const hasVideo = current.querySelectorAll("video").length > 0;
      const hasSinaimg = current.querySelectorAll("img[src*='sinaimg']").length > 0;
      const hasAuthorLink = current.querySelectorAll("a[href*='/u/']").length > 0;
      const childCount = current.children.length;

      ancestorChain.push({
        tag: current.tagName.toLowerCase(),
        className: current.className || "",
        childCount,
        hasVideo,
        hasSinaimg,
        hasAuthorLink,
      });

      // 推测帖子完整容器：第一个同时含媒体+作者链接的祖先
      // （含正文+媒体+作者的容器大概率是帖子本身）
      if (!postContainer && (hasVideo || hasSinaimg) && hasAuthorLink) {
        postContainer = current;
      }

      current = current.parentElement;
    }

    // 采集推测的帖子容器 outerHTML 预览
    let postContainerPreview: string | undefined;
    if (postContainer) {
      postContainerPreview = postContainer.outerHTML.slice(0, 3000);
    }

    samples.push({
      text,
      textClassName,
      ancestorChain,
      postContainerPreview,
    });
  }

  return {
    postCount: wbtextEls.length,
    samples,
  };
}

/**
 * 微博专用：读取 __INITIAL_STATE__（weibo.com PC 版有此结构）
 *
 * ★ 微博 __INITIAL_STATE__ 在 isolated JS 上下文不可见，需通过 background
 *   中转到 MAIN world 读取（复用 xhs-read-state 通道，但微博不裁剪）
 *
 * ★ 通道复用：xhs-read-state 在 background 端用 chrome.scripting.executeScript
 *   在 MAIN world 执行 window.__INITIAL_STATE__ 读取，对微博同样适用
 *   （__INITIAL_STATE__ 是通用 SSR 数据结构）
 */
function readWeiboInitialState(timeout = 3000): Promise<unknown> {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage({ type: "weibo-read-state" }, (state) => {
        if (chrome.runtime.lastError) {
          console.log("[Lumio-diag] weibo-read-state 错误:", chrome.runtime.lastError.message);
          resolve({ __error: chrome.runtime.lastError.message });
          return;
        }
        resolve(state || { __error: "empty" });
      });
      setTimeout(() => resolve({ __error: "timeout" }), timeout);
    } catch (e) {
      resolve({ __error: String(e) });
    }
  });
}

/**
 * 微博专用：读取 $render_data（m.weibo.cn 移动版 SSR）
 *
 * m.weibo.cn 部分页面用 <script>$render_data = {...}</script> 形式存储 SSR
 * 这是 inline script 全局变量，在 MAIN world 可见，isolated 不可见
 * 通过 background 中转读取
 */
function readWeiboRenderData(timeout = 3000): Promise<unknown> {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage({ type: "weibo-read-render-data" }, (data) => {
        if (chrome.runtime.lastError) {
          console.log("[Lumio-diag] weibo-read-render-data 错误:", chrome.runtime.lastError.message);
          resolve({ __error: chrome.runtime.lastError.message });
          return;
        }
        resolve(data || { __error: "empty" });
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
 * 读取抖音 RENDER_DATA（content script 在 isolated world，可直接读 <script> textContent）
 * RENDER_DATA 是 URL 编码的 JSON，需先 decodeURIComponent 再 JSON.parse
 * 顶层 key 不固定（'43' / '44' / 哈希），需遍历找含 aweme.detail 的 key
 */
function readDouyinRenderData(): unknown {
  try {
    const script = document.querySelector("script#RENDER_DATA");
    if (!script?.textContent) {
      return { __error: "RENDER_DATA script 标签未找到" };
    }
    const raw = script.textContent;
    let decoded: string;
    try {
      decoded = decodeURIComponent(raw);
    } catch (e) {
      return { __error: `decodeURIComponent 失败: ${String(e)}`, rawPreview: raw.slice(0, 500) };
    }
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(decoded);
    } catch (e) {
      return { __error: `JSON.parse 失败: ${String(e)}`, decodedPreview: decoded.slice(0, 500) };
    }

    // 顶层 key 不固定，遍历找含 aweme.detail 的那个
    const topKeys = Object.keys(data);
    for (const key of topKeys) {
      const entry = data[key] as {
        aweme?: { detail?: unknown } | null;
      } | undefined;
      const detail = entry?.aweme?.detail;
      if (detail) {
        return {
          topKeys,
          matchedKey: key,
          detail,
        };
      }
    }
    // aweme 字段被 null 化反爬
    return {
      topKeys,
      __aweme_null_or_missing: true,
      // 输出第一个 key 的顶层结构，帮助定位
      firstEntryPreview: data[topKeys[0]]
        ? JSON.parse(JSON.stringify(data[topKeys[0]])) // 深拷贝避免循环引用
        : null,
    };
  } catch (e) {
    return { __error: String(e) };
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
        : platform === "douyin"
          ? DOUYIN_SELECTORS
          : platform === "weibo"
            ? WEIBO_SELECTORS
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
  // ★ 抖音聚焦策略：只采集 feed-active-video 容器内的 video/img，避免推荐页数据冗余
  // ★ 微博聚焦策略：优先采集详情容器内的 video/img，避免推荐区/评论区数据冗余
  const weiboDetailSelector =
    "[class*='detail_wbtext'], [node-type='feed_list_content'], .weibo-text, [class*='wbtext']";
  const videos =
    platform === "douyin"
      ? collectVideosFromContainer("[data-e2e='feed-active-video']")
      : platform === "weibo"
        ? collectVideosFromContainer(weiboDetailSelector)
        : collectVideos();
  const images =
    platform === "douyin"
      ? collectImagesFromContainer("[data-e2e='feed-active-video']")
      : platform === "weibo"
        ? collectImagesFromContainer(weiboDetailSelector)
        : collectImages();
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

  // 5. 平台特定：抖音 RENDER_DATA（URL 编码的 SSR JSON）
  let renderData: unknown;
  if (platform === "douyin") {
    notes.push("抖音：读取 <script id=RENDER_DATA> SSR 数据");
    console.log("[Lumio-diag] 读取 RENDER_DATA...");
    renderData = readDouyinRenderData();
    const r = renderData as { __error?: string; __aweme_null_or_missing?: boolean; matchedKey?: string } | null;
    if (r?.__error) {
      notes.push(`⚠️ RENDER_DATA 读取异常: ${r.__error}`);
    } else if (r?.__aweme_null_or_missing) {
      notes.push("⚠️ RENDER_DATA 中 aweme.detail 为 null 或缺失（抖音反爬 null 化），提取将 fallback 到 og 标签");
    } else if (r?.matchedKey) {
      notes.push(`✅ RENDER_DATA 命中 key=${r.matchedKey}`);
    }
  }

  // 5.5 平台特定：微博 __INITIAL_STATE__ + $render_data
  // ★ weibo.com PC 版用 __INITIAL_STATE__（React SSR）
  // ★ m.weibo.cn 移动版用 $render_data（inline script 全局变量）
  // 两者都在 isolated JS 不可见，需 background 中转读取
  let weiboInitialState: unknown;
  let weiboRenderData: unknown;
  if (platform === "weibo") {
    const isMobile = window.location.hostname.includes("m.weibo.cn");

    if (isMobile) {
      notes.push("微博移动版 (m.weibo.cn)：读取 $render_data SSR 数据");
      console.log("[Lumio-diag] 读取 weibo $render_data...");
      weiboRenderData = await readWeiboRenderData(3000);
      const r = weiboRenderData as { __error?: string } | null;
      if (r?.__error) {
        notes.push(`⚠️ $render_data 读取异常: ${r.__error}`);
      } else if (weiboRenderData && typeof weiboRenderData === "object") {
        notes.push("✅ $render_data 读取成功");
      }
    } else {
      notes.push("微博 PC 版 (weibo.com)：读取 __INITIAL_STATE__ SSR 数据");
      console.log("[Lumio-diag] 读取 weibo __INITIAL_STATE__...");
      weiboInitialState = await readWeiboInitialState(3000);
      const r = weiboInitialState as { __error?: string } | null;
      if (r?.__error) {
        notes.push(`⚠️ __INITIAL_STATE__ 读取异常: ${r.__error}`);
      } else if (weiboInitialState && typeof weiboInitialState === "object") {
        notes.push("✅ __INITIAL_STATE__ 读取成功");
      }
    }
  }

  // 6. 平台特定：小红书媒体容器 DOM 结构（诊断当前帖子媒体渲染方式）
  let mediaContainerDom: DiagnoseReport["mediaContainerDom"];
  if (platform === "xiaohongshu") {
    mediaContainerDom = collectMediaContainerDom();
    console.log("[Lumio-diag] mediaContainerDom 子元素数:", mediaContainerDom.childElements.length);
  }

  // 6.5 平台特定：抖音媒体容器 DOM + xgplayer 播放器信息
  // ★ 抖音 DOM 与小红书完全不同：
  //   - 视频页用 [data-e2e="feed-active-video"] 包裹当前激活视频
  //   - 图文笔记页用 [data-e2e="note-container"] 包裹图片轮播
  //   - 视频播放器是 xgplayer 自定义元素（<xgplayer> / <xg-video>）
  // 采集这些信息用于诊断 RENDER_DATA 失效时的 DOM fallback 路径
  let douyinMediaDom: DiagnoseReport["douyinMediaDom"];
  let douyinPlayer: DiagnoseReport["douyinPlayer"];
  let douyinDataE2eValues: DiagnoseReport["douyinDataE2eValues"];
  if (platform === "douyin") {
    douyinMediaDom = collectDouyinMediaDom();
    console.log(
      "[Lumio-diag] douyinMediaDom pageType=",
      douyinMediaDom.pageType,
      "matched=",
      douyinMediaDom.matchedSelector,
      "子元素数:",
      douyinMediaDom.childElements.length,
    );
    if (douyinMediaDom.matchedSelector) {
      notes.push(`✅ 抖音媒体容器命中: ${douyinMediaDom.matchedSelector}（pageType=${douyinMediaDom.pageType}）`);
    } else {
      notes.push(`⚠️ 未找到抖音媒体容器（pageType=${douyinMediaDom.pageType}），可能 DOM 改版或选择器失效`);
    }

    douyinPlayer = collectDouyinPlayer();
    console.log("[Lumio-diag] douyinPlayer found=", douyinPlayer.found, "tag=", douyinPlayer.tag);
    if (douyinPlayer.found) {
      notes.push(`✅ 播放器元素: <${douyinPlayer.tag}> (class=${douyinPlayer.className || "(空)"})`);
      if (douyinPlayer.videoPoster) {
        notes.push(`✅ video.poster 存在，可作为缩略图 fallback`);
      }
      if (douyinPlayer.videoSrc.startsWith("blob:")) {
        notes.push("⚠️ video.src 是 blob: URL（无法直链下载，必须从 RENDER_DATA 或后端 API 拿直链）");
      } else if (douyinPlayer.videoSrc) {
        notes.push(`✅ video.src 是 http URL（可能含 x-expires 时效签名）`);
      }
    } else {
      // 图文笔记页通常没有 video 元素，不算异常
      if (/\/note\//.test(url)) {
        notes.push("ℹ️ 图文笔记页无 video 元素（正常）");
      } else {
        notes.push("⚠️ 视频页未找到 xgplayer/xg-video/video 元素（可能 SPA 未渲染完成）");
      }
    }

    // ★ 采集所有 [data-e2e] 元素的值列表（便于定位作者/标题等元素的真实选择器）
    // 诊断数据显示 [data-e2e='video-author-nickname'] 0 命中，需要找真正的作者选择器
    const e2eMap = new Map<string, { count: number; firstEl: Element }>();
    document.querySelectorAll("[data-e2e]").forEach((el) => {
      const val = el.getAttribute("data-e2e") || "";
      if (!val) return;
      const existing = e2eMap.get(val);
      if (existing) {
        existing.count++;
      } else {
        e2eMap.set(val, { count: 1, firstEl: el });
      }
    });
    douyinDataE2eValues = Array.from(e2eMap.entries())
      .map(([value, { count, firstEl }]) => ({
        value,
        count,
        firstMatch: {
          tag: firstEl.tagName.toLowerCase(),
          className: firstEl.className || "",
          textPreview: (firstEl.textContent || "").trim().slice(0, 100),
        },
      }))
      .sort((a, b) => b.count - a.count);
    console.log("[Lumio-diag] data-e2e 值种类数:", douyinDataE2eValues.length);
  }

  // 6.6 平台特定：微博媒体容器 DOM 结构
  // ★ 微博 DOM 与抖音/小红书完全不同：
  //   - weibo.com PC 版用 React 渲染，[node-type='feed_list_content'] 包正文
  //   - m.weibo.cn 移动版用 .weibo-text 包正文，.weibo-top 包作者
  //   - 视频/图片/livephoto 在主贴区域，但选择器因版本而异
  // 采集这些信息用于诊断 SSR 失效时的 DOM fallback 路径
  let weiboMediaDom: DiagnoseReport["weiboMediaDom"];
  let weiboPosts: DiagnoseReport["weiboPosts"];
  if (platform === "weibo") {
    weiboMediaDom = collectWeiboMediaDom();
    console.log(
      "[Lumio-diag] weiboMediaDom pageType=",
      weiboMediaDom.pageType,
      "matched=",
      weiboMediaDom.matchedSelector,
      "子元素数:",
      weiboMediaDom.childElements.length,
    );
    if (weiboMediaDom.matchedSelector) {
      notes.push(`✅ 微博媒体容器命中: ${weiboMediaDom.matchedSelector}（pageType=${weiboMediaDom.pageType}）`);
    } else {
      notes.push(`⚠️ 未找到微博媒体容器（pageType=${weiboMediaDom.pageType}），可能 DOM 改版或选择器失效`);
    }

    // ★ 关键采集：微博帖子列表结构（博主主页流式列表）
    // 通过 .wbtext 向上找帖子完整容器，确认帖子容器的 class 模式
    weiboPosts = collectWeiboPosts();
    if (weiboPosts) {
      console.log(
        "[Lumio-diag] weiboPosts postCount=",
        weiboPosts.postCount,
        "samples=",
        weiboPosts.samples.length,
      );
      if (weiboPosts.postCount > 0) {
        notes.push(`ℹ️ 检测到 ${weiboPosts.postCount} 个微博帖子（.wbtext）`);
        // 检查第一个样本是否找到帖子完整容器
        const firstSample = weiboPosts.samples[0];
        if (firstSample?.postContainerPreview) {
          notes.push("✅ 成功定位帖子完整容器（含正文+媒体+作者链接）");
        } else if (firstSample) {
          // 找不到完整容器时，输出祖先链帮助定位
          const chainInfo = firstSample.ancestorChain
            .map((a, idx) => `[${idx}]=${a.tag}.${a.className.slice(0, 30)}(v=${a.hasVideo},img=${a.hasSinaimg},author=${a.hasAuthorLink})`)
            .join(" → ");
          notes.push(`⚠️ 未定位到帖子完整容器，祖先链：${chainInfo}`);
        }
      } else {
        notes.push("⚠️ 未检测到微博帖子（.wbtext 0 命中），可能 DOM 改版");
      }
    }

    // 检测 video.src 是否为 blob:
    const vids = weiboMediaDom.childElements.filter(
      (c) => c.tag === "video" && c.src,
    );
    if (vids.length > 0) {
      const firstSrc = vids[0].src || "";
      if (firstSrc.startsWith("blob:")) {
        notes.push("⚠️ video.src 是 blob: URL（无法直链下载，必须从 SSR 数据或后端 API 拿直链）");
      } else if (firstSrc.startsWith("http")) {
        notes.push("✅ video.src 是 http URL（可能含签名时效，需尽快下载）");
      }
    }

    // 检测 sinaimg.cn 图片是否需要 Cookie
    const imgs = weiboMediaDom.childElements.filter(
      (c) => c.tag === "img" && c.src && c.src.includes("sinaimg"),
    );
    if (imgs.length > 0) {
      notes.push(`ℹ️ 检测到 ${imgs.length} 张 sinaimg.cn 图片，下载需 Cookie (SUB/SUBP) + Referer`);
    }
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
  if (platform === "douyin") {
    // 区分视频页/图文笔记页/modal 模式（DOM 结构和提取策略不同）
    const isNotePage = /\/note\//.test(url);
    const isVideoPage = /\/video\//.test(url);
    const isModalPage = /[?&]modal_id=/.test(url);
    if (isNotePage) {
      notes.push("ℹ️ 当前为抖音图文笔记页 (/note/{id})，提取图片列表为主");
    } else if (isVideoPage) {
      notes.push("ℹ️ 当前为抖音视频详情页 (/video/{id})，提取视频元数据为主");
    } else if (isModalPage) {
      notes.push("ℹ️ 当前为抖音 modal 模式 (?modal_id={id})，精选页/关注页点视频弹出");
    } else {
      notes.push("⚠️ 当前 URL 不是 /video/ 也不是 /note/ 也不是 modal_id，extractDouyin 会返回 null");
    }

    if (selectors["[data-e2e]"] === 0) {
      notes.push("⚠️ [data-e2e] 选择器 0 命中，可能 DOM 改版");
    }
    if (videos.length > 0 && videos.every((v) => v.src.startsWith("blob:"))) {
      notes.push("⚠️ video 全为 blob: URL，直链必须从 RENDER_DATA 提取（无法用 <video>.src 下载）");
    }
    if (selectors["img[src*='douyinpic']"] === 0 && selectors["img[src*='bytecdn']"] === 0) {
      // 图文笔记页才会依赖图片 CDN
      if (isNotePage) {
        notes.push("⚠️ 图文笔记页抖音 CDN 图片选择器 0 命中（可能懒加载未触发或 DOM 改版）");
      }
    }
    // SPA 时序检测：RENDER_DATA 可能在路由变化后才注入
    if (selectors["script#RENDER_DATA"] === 0) {
      notes.push("⚠️ script#RENDER_DATA 未找到（SPA 可能未渲染完成，或页面非详情页）");
    }
    // 反爬检测：RENDER_DATA 存在但 aweme.detail 为 null
    const r = renderData as { __aweme_null_or_missing?: boolean; matchedKey?: string; __error?: string } | null;
    if (r?.__aweme_null_or_missing) {
      if (isModalPage) {
        notes.push("⚠️ modal 模式下 RENDER_DATA 不含 aweme.detail（精选页 SSR 只含应用配置，需走 DOM fallback）");
      } else {
        notes.push("⚠️ 检测到抖音反爬：RENDER_DATA 存在但 aweme.detail 被 null 化");
      }
    }
  }
  if (platform === "instagram") {
    if (selectors["img[src*='cdninstagram']"] === 0 && selectors["img[src*='fbcdn']"] === 0) {
      notes.push("⚠️ IG CDN 选择器全部 0 命中，可能 DOM 改版或未登录");
    }
  }
  if (platform === "weibo") {
    // 区分 PC 版 / 移动版 / 详情页（DOM 结构不同）
    const isPc = window.location.hostname.includes("weibo.com") && !window.location.hostname.includes("m.weibo.cn");
    const isMobile = window.location.hostname.includes("m.weibo.cn");
    const isDetailPage = /weibo\.com\/\d+\/[a-zA-Z0-9]+/.test(url) ||
      /m\.weibo\.cn\/(status|detail)\/[a-zA-Z0-9]+/.test(url) ||
      /weibo\.com\/detail\/[a-zA-Z0-9]+/.test(url);
    if (isPc) {
      notes.push("ℹ️ 当前为微博 PC 版 (weibo.com)");
    } else if (isMobile) {
      notes.push("ℹ️ 当前为微博移动版 (m.weibo.cn)");
    }
    if (!isDetailPage) {
      notes.push("⚠️ 当前 URL 不是微博详情页，extractWeibo 会返回 null");
    }

    // 检测关键选择器命中
    if (selectors["[node-type='feed_list_content']"] === 0 &&
        selectors[".weibo-text"] === 0 &&
        selectors["[class*='wbtext']"] === 0) {
      notes.push("⚠️ 微博正文容器选择器全部 0 命中，可能 DOM 改版");
    }
    if (selectors["img[src*='sinaimg']"] === 0 && selectors["video[poster]"] === 0) {
      notes.push("⚠️ sinaimg.cn 图片和 video.poster 全部 0 命中，缩略图可能拿不到");
    }
    if (selectors["a[href*='/u/']"] === 0 && selectors["[class*='username']"] === 0) {
      notes.push("⚠️ 作者选择器全部 0 命中，author 字段可能为空");
    }
    // 检测 og 标签
    if (!metaInfo.ogTitle && !metaInfo.ogImage) {
      notes.push("⚠️ og:title 和 og:image 均为空，可能页面非详情页或 SSR 未渲染");
    }
    // 检测 video 元素 blob: 状态
    if (videos.length > 0 && videos.every((v) => v.src.startsWith("blob:"))) {
      notes.push("⚠️ video 全为 blob: URL，直链必须从 SSR 或后端 API 拿（浏览器侧无法直链下载）");
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
    renderData,
    mediaContainerDom,
    douyinMediaDom,
    douyinPlayer,
    douyinDataE2eValues,
    weiboMediaDom,
    weiboInitialState,
    weiboRenderData,
    weiboPosts,
    notes,
  };
}
