/**
 * 右键菜单管理
 *
 * 4 个菜单项：页面 / 链接 / 视频 / 图片
 * 阶段 1：仅发 URL（不调 content.js）
 * 阶段 2：接入 content.js 元数据
 */
import type { CapturePayload, PageMeta } from "../types";
import { detectPlatform, extractAuthorFromUrl } from "./api-client";

const MENU_ITEMS = [
  { id: "lumio-capture-page", title: "发送当前页面到 Lumio", contexts: ["page"] as const },
  { id: "lumio-capture-link", title: "发送链接到 Lumio", contexts: ["link"] as const },
  { id: "lumio-capture-video", title: "发送视频到 Lumio", contexts: ["video"] as const },
  { id: "lumio-capture-image", title: "发送图片到 Lumio", contexts: ["image"] as const },
];

export function createContextMenus() {
  // onInstalled 时调用
  for (const item of MENU_ITEMS) {
    chrome.contextMenus.create({
      id: item.id,
      title: item.title,
      contexts: [...item.contexts],
    });
  }
}

/** 构建 capture 载荷 */
export function buildCapturePayload(
  menuItemId: string,
  info: chrome.contextMenus.OnClickData,
  tab: chrome.tabs.Tab,
  pageMeta: PageMeta | null,
): CapturePayload | null {
  const isVideo = menuItemId === "lumio-capture-video";

  switch (menuItemId) {
    case "lumio-capture-page": {
      // 阶段 1：用 pageMeta 或裸 URL
      if (pageMeta && pageMeta.url) {
        return {
          url: pageMeta.url,
          title: pageMeta.title || tab.title || "",
          author: pageMeta.author || "",
          platform: pageMeta.platform || detectPlatform(tab.url || ""),
          thumbnail: pageMeta.thumbnail || "",
          duration: pageMeta.duration || null,
          source: "browser",
          type: pageMeta.type || "url",
        };
      }
      return {
        url: tab.url || "",
        title: tab.title || "",
        author: "",
        platform: detectPlatform(tab.url || ""),
        thumbnail: "",
        duration: null,
        source: "browser",
        type: "url",
      };
    }

    case "lumio-capture-link":
      return {
        url: info.linkUrl || "",
        title: info.selectionText || info.linkUrl || "",
        author: extractAuthorFromUrl(info.linkUrl || ""),
        platform: detectPlatform(info.linkUrl || ""),
        thumbnail: "",
        duration: null,
        source: "browser",
        type: "url",
      };

    case "lumio-capture-video":
    case "lumio-capture-image": {
      // 阶段 1：优先用 pageMeta，否则用 srcUrl 作为 direct_url
      if (pageMeta && pageMeta.url && pageMeta.platform) {
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
      const srcUrl = info.srcUrl || "";
      if (!srcUrl) return null;
      return {
        url: tab.url || srcUrl,
        title: isVideo ? tab.title || "Video" : (info as chrome.contextMenus.OnClickData & { alt?: string }).alt || tab.title || "Image",
        author: "",
        platform: detectPlatform(tab.url || ""),
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
