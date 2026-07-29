/**
 * 右键菜单管理（阶段 4：上下文感知）
 *
 * 4 个菜单项：页面 / 链接 / 视频 / 图片
 *
 * 上下文感知策略：
 *   - 详情页（/watch, /p/, /status/, /explore/, /video/BV）：
 *     - page 项 → "发送当前帖子到 Lumio"
 *     - image 项 → 智能判断：图在媒体容器内 → 发整帖；否则 → 发该图
 *     - video 项 → 智能判断：视频是当前帖子 → 发整帖；否则 → 发该视频
 *     - link 项 → 智能判断：链接是平台帖子 URL → 发该帖子；否则 → 发链接
 *   - 博主主页（/channel/, /user/, /c/, /profile/）：
 *     - page 项 → "发送博主主页到 Lumio"（触发批量）
 *     - 其他项按默认行为
 *   - 非支持平台：所有菜单项隐藏
 *
 * 实现：chrome.contextMenus.onShown（MV3）+ 动态 update 标题/可见性
 */
import type { CapturePayload, PageMeta, Platform } from "../types";
import { detectPlatform, extractAuthorFromUrl } from "./api-client";

const MENU_ITEMS = [
  { id: "lumio-capture-page", title: "发送当前页面到 Lumio", contexts: ["page"] as const },
  { id: "lumio-capture-link", title: "发送链接到 Lumio", contexts: ["link"] as const },
  { id: "lumio-capture-video", title: "发送视频到 Lumio", contexts: ["video"] as const },
  { id: "lumio-capture-image", title: "发送图片到 Lumio", contexts: ["image"] as const },
];

/**
 * 菜单只在支持平台显示（静态限制，不依赖 onShown）
 * ★ onShown 仅 Chrome 121+ 支持，低版本浏览器不会隐藏菜单
 * documentUrlPatterns 用 match patterns，Chrome 原生支持，所有版本都生效
 */
const SUPPORTED_PATTERNS = [
  "*://*.youtube.com/*",
  "*://*.youtu.be/*",
  "*://*.instagram.com/*",
  "*://*.x.com/*",
  "*://*.twitter.com/*",
  "*://*.bilibili.com/*",
  "*://*.b23.tv/*",
  "*://*.kuaishou.com/*",
  "*://*.xiaohongshu.com/*",
];

export function createContextMenus() {
  // onInstalled 时调用
  for (const item of MENU_ITEMS) {
    chrome.contextMenus.create({
      id: item.id,
      title: item.title,
      contexts: [...item.contexts],
      documentUrlPatterns: SUPPORTED_PATTERNS,
    });
  }
}

// ── 页面类型识别 ──────────────────────────────────────────────────────

/** 判断是否为详情页（与 shared/detailPage.ts 保持一致，但加抖音/快手） */
function isDetailPageUrl(url: string): boolean {
  if (!url) return false;
  return (
    url.includes("/watch") || // YouTube
    /\/(p|reel)\//.test(url) || // Instagram
    /\/status\//.test(url) || // X
    /\/video\/(BV|av)/i.test(url) || // B站
    /\/(explore|discovery\/item)\//.test(url) || // 小红书
    /\/note\//.test(url) || // 小红书笔记
    /douyin\.com\/video\//.test(url) || // 抖音视频
    /douyin\.com\/note\//.test(url) || // 抖音图文
    /kuaishou\.com\/short-video\//.test(url) || // 快手
    /weibo\.com\/\d+\/[A-Za-z0-9]+/.test(url) // 微博
  );
}

/** 判断是否为博主主页 */
function isProfilePageUrl(url: string): boolean {
  if (!url) return false;
  return (
    /youtube\.com\/(@|channel|user|c)\//.test(url) || // YouTube
    /instagram\.com\/[^/]+\/?$/.test(url) || // Instagram
    /instagram\.com\/[^/]+\/?\?/.test(url) ||
    /x\.com\/[^/]+\/?$/.test(url) || // X
    /twitter\.com\/[^/]+\/?$/.test(url) ||
    /space\.bilibili\.com\/\d+/.test(url) || // B站
    /xiaohongshu\.com\/user\/profile\//.test(url) || // 小红书
    /douyin\.com\/user\//.test(url) || // 抖音
    /kuaishou\.com\/profile\//.test(url) || // 快手
    /weibo\.com\/u\/\d+/.test(url) || // 微博
    /weibo\.com\/[^/]+\/?$/.test(url)
  );
}

/** 判断 URL 是否为平台帖子链接（用于右键链接场景） */
function isPlatformPostUrl(url: string): boolean {
  return isDetailPageUrl(url);
}

/** 判断 URL 是否为博主主页链接（用于右键链接场景） */
function isProfileUrl(url: string): boolean {
  return isProfilePageUrl(url);
}

// ── 菜单标题动态生成 ──────────────────────────────────────────────────

/** 平台中文名 */
function platformLabel(platform: Platform): string {
  switch (platform) {
    case "youtube":
      return "YouTube";
    case "instagram":
      return "Instagram";
    case "x":
      return "X";
    case "bilibili":
      return "B站";
    case "kuaishou":
      return "快手";
    case "xiaohongshu":
      return "小红书";
    default:
      return "";
  }
}

/** 根据上下文生成 page 项标题 */
function pageMenuItemTitle(url: string, platform: Platform): string {
  if (isDetailPageUrl(url)) {
    return `发送当前${platformLabel(platform)}帖子到 Lumio`;
  }
  if (isProfilePageUrl(url)) {
    return `发送${platformLabel(platform)}博主主页到 Lumio（批量）`;
  }
  return "发送当前页面到 Lumio";
}

/** 根据上下文生成 link 项标题 */
function linkMenuItemTitle(linkUrl: string): string {
  if (isPlatformPostUrl(linkUrl)) {
    const platform = detectPlatform(linkUrl);
    return `发送此${platformLabel(platform)}帖子链接到 Lumio`;
  }
  if (isProfileUrl(linkUrl)) {
    const platform = detectPlatform(linkUrl);
    return `发送此${platformLabel(platform)}博主主页到 Lumio（批量）`;
  }
  return "发送链接到 Lumio";
}

// ── onShown 动态菜单 ──────────────────────────────────────────────────

/**
 * 在菜单显示前动态调整菜单项标题和可见性
 * 在 background/index.ts 里绑定到 chrome.contextMenus.onShown
 */
export function updateContextMenuOnShown(
  info: chrome.contextMenus.OnClickData,
  tab: chrome.tabs.Tab | undefined,
): void {
  const tabUrl = tab?.url || "";
  const platform = detectPlatform(tabUrl);

  // 非支持平台：隐藏所有菜单项
  if (!platform) {
    for (const item of MENU_ITEMS) {
      chrome.contextMenus.update(item.id, { visible: false });
    }
    return;
  }

  // page 项：根据页面类型动态标题
  const pageTitle = pageMenuItemTitle(tabUrl, platform);
  chrome.contextMenus.update("lumio-capture-page", {
    title: pageTitle,
    visible: true,
  });

  // link 项：根据链接 URL 动态标题
  if (info.linkUrl) {
    chrome.contextMenus.update("lumio-capture-link", {
      title: linkMenuItemTitle(info.linkUrl),
      visible: true,
    });
  } else {
    chrome.contextMenus.update("lumio-capture-link", { visible: false });
  }

  // image 项：详情页右键图片时显示"发送整帖"
  if (info.mediaType === "image" && info.srcUrl) {
    if (isDetailPageUrl(tabUrl)) {
      chrome.contextMenus.update("lumio-capture-image", {
        title: `发送当前${platformLabel(platform)}帖子到 Lumio`,
        visible: true,
      });
    } else {
      chrome.contextMenus.update("lumio-capture-image", {
        title: "发送图片到 Lumio",
        visible: true,
      });
    }
  } else {
    chrome.contextMenus.update("lumio-capture-image", { visible: false });
  }

  // video 项：详情页右键视频时显示"发送整帖"
  if (info.mediaType === "video") {
    if (isDetailPageUrl(tabUrl)) {
      chrome.contextMenus.update("lumio-capture-video", {
        title: `发送当前${platformLabel(platform)}帖子到 Lumio`,
        visible: true,
      });
    } else {
      chrome.contextMenus.update("lumio-capture-video", {
        title: "发送视频到 Lumio",
        visible: true,
      });
    }
  } else {
    chrome.contextMenus.update("lumio-capture-video", { visible: false });
  }
}

// ── 载荷构建 ──────────────────────────────────────────────────────────

/** 构建 capture 载荷（阶段 4：上下文感知） */
export function buildCapturePayload(
  menuItemId: string,
  info: chrome.contextMenus.OnClickData,
  tab: chrome.tabs.Tab,
  pageMeta: PageMeta | null,
): CapturePayload | null {
  const isVideo = menuItemId === "lumio-capture-video";
  const tabUrl = tab.url || "";
  const platform = detectPlatform(tabUrl);

  switch (menuItemId) {
    case "lumio-capture-page": {
      // 详情页：优先用 pageMeta
      if (isDetailPageUrl(tabUrl)) {
        if (pageMeta && pageMeta.url) {
          return {
            url: pageMeta.url,
            title: pageMeta.title || tab.title || "",
            author: pageMeta.author || "",
            platform: pageMeta.platform || platform,
            thumbnail: pageMeta.thumbnail || "",
            duration: pageMeta.duration || null,
            source: "browser",
            type: pageMeta.type || "url",
          };
        }
        // pageMeta 提取失败时仍发 URL（由后端再提取）
        return {
          url: tabUrl,
          title: tab.title || "",
          author: "",
          platform,
          thumbnail: "",
          duration: null,
          source: "browser",
          type: "url",
        };
      }

      // 博主主页：发送主页 URL，type=profile 触发后端批量
      if (isProfilePageUrl(tabUrl)) {
        return {
          url: tabUrl,
          title: tab.title || "",
          author: extractAuthorFromUrl(tabUrl),
          platform,
          thumbnail: "",
          duration: null,
          source: "browser",
          type: "profile",
        };
      }

      // 其他页面：发裸 URL
      return {
        url: tabUrl,
        title: tab.title || "",
        author: "",
        platform: platform || "",
        thumbnail: "",
        duration: null,
        source: "browser",
        type: "url",
      };
    }

    case "lumio-capture-link": {
      const linkUrl = info.linkUrl || "";
      // 链接是平台帖子 URL → 发送该帖子
      if (isPlatformPostUrl(linkUrl)) {
        return {
          url: linkUrl,
          title: info.selectionText || linkUrl,
          author: extractAuthorFromUrl(linkUrl),
          platform: detectPlatform(linkUrl),
          thumbnail: "",
          duration: null,
          source: "browser",
          type: "url",
        };
      }
      // 链接是博主主页 URL → 触发批量
      if (isProfileUrl(linkUrl)) {
        return {
          url: linkUrl,
          title: info.selectionText || linkUrl,
          author: extractAuthorFromUrl(linkUrl),
          platform: detectPlatform(linkUrl),
          thumbnail: "",
          duration: null,
          source: "browser",
          type: "profile",
        };
      }
      // 普通链接
      return {
        url: linkUrl,
        title: info.selectionText || linkUrl,
        author: "",
        platform: detectPlatform(linkUrl) || "",
        thumbnail: "",
        duration: null,
        source: "browser",
        type: "url",
      };
    }

    case "lumio-capture-video":
    case "lumio-capture-image": {
      // 详情页右键图片/视频：优先发整帖（用 pageMeta）
      if (isDetailPageUrl(tabUrl) && pageMeta && pageMeta.url && pageMeta.platform) {
        return {
          url: pageMeta.url,
          title: pageMeta.title || tab.title || "",
          author: pageMeta.author || "",
          platform: pageMeta.platform,
          thumbnail: pageMeta.thumbnail || "",
          duration: pageMeta.duration || null,
          source: "browser",
          type: isVideo ? "video" : "image",
        };
      }

      // 非详情页 / pageMeta 不可用：用 srcUrl 作为 direct_url
      const srcUrl = info.srcUrl || "";
      if (!srcUrl) return null;
      return {
        url: tabUrl || srcUrl,
        title: isVideo
          ? tab.title || "Video"
          : (info as chrome.contextMenus.OnClickData & { alt?: string }).alt ||
            tab.title ||
            "Image",
        author: "",
        platform: platform || "",
        thumbnail: "",
        duration: null,
        source: "browser",
        type: isVideo ? "video" : "image",
        direct_url: srcUrl,
      };
    }
  }

  return null;
}

/** 带超时的 sendMessage，防止 content.js 未响应时 hang 住 */
export async function safeTabsMessage<T = unknown>(
  tabId: number,
  message: unknown,
  timeoutMs = 1500,
): Promise<T | null> {
  try {
    const result = await Promise.race([
      chrome.tabs.sendMessage(tabId, message),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("sendMessage timeout")), timeoutMs),
      ),
    ]);
    return result as T;
  } catch {
    return null;
  }
}
