/**
 * Lumio Extension Background Service Worker
 *
 * 职责：
 * 1. 健康轮询（5s）→ 广播连接状态给 popup
 * 2. 右键菜单注册 + 点击处理
 * 3. 接收 popup capture 请求 → 转发到 Lumio FastAPI
 * 4. 设置管理（API base URL、主题）
 *
 * 阶段 1：基础功能
 * 阶段 2：content.js 元数据集成
 * 阶段 3：commands + omnibox + WebSocket
 */
import type { CapturePayload, CaptureResult, LumioSettings, PageMeta } from "../types";
import { LumioClient, detectPlatform, extractAuthorFromUrl } from "./api-client";
import {
  createContextMenus,
  buildCapturePayload,
  safeTabsMessage,
  updateContextMenuOnShown,
} from "./contextMenus";
import { DEFAULT_SETTINGS, getSettings, saveSettings } from "./settings";
import { isDetailPageUrl } from "../shared/detailPage";
import {
  saveToHistory,
  getRecentHistory,
  getHistoryItem,
  deleteHistoryItem,
  deleteHistoryItems,
  clearHistory,
  getHistoryCount,
} from "./history";

// ── 客户端实例 ────────────────────────────────────────────────────────

let client = new LumioClient(DEFAULT_SETTINGS.apiBaseUrl);
let connected = false;

// ★ MV3 Service Worker 会在空闲时被销毁，再次唤醒时顶层代码重新执行。
// 此时 client 会用 DEFAULT_SETTINGS.apiBaseUrl 初始化，getSettings() 是异步的，
// 如果 checkHealth/capture 在 settings 加载完成前执行，会用到默认端口。
// 修复：保存 settings 加载 Promise，所有请求前 await 它。
const settingsReady = getSettings().then((settings) => {
  client.updateBaseUrl(settings.apiBaseUrl);
  return settings;
});

// ── 健康轮询 ──────────────────────────────────────────────────────────

async function checkHealth() {
  await settingsReady; // 确保 settings 已加载，避免用默认端口
  connected = await client.health();
  chrome.runtime.sendMessage({ type: "status", connected }).catch(() => {});
}

setInterval(checkHealth, 5000);
checkHealth();

// ── 安装时创建右键菜单 ────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  createContextMenus();
});

// ── 右键菜单显示前动态调整（阶段 4：上下文感知）─────────────────────
// ★ onShown 仅 Chrome 121+ / Edge 121+ 支持，Firefox 不支持
// 必须运行时检查存在性，否则旧版浏览器 SW 启动失败导致插件离线
// @types/chrome 未包含 onShown 事件，需类型断言绕过编译检查

type ContextMenusWithOnShown = typeof chrome.contextMenus & {
  onShown?: {
    addListener: (
      cb: (info: chrome.contextMenus.OnClickData, tab: chrome.tabs.Tab) => void,
    ) => void;
  };
};

const cm = chrome.contextMenus as ContextMenusWithOnShown | undefined;
if (cm && cm.onShown) {
  cm.onShown.addListener((info, tab) => {
    try {
      updateContextMenuOnShown(info, tab);
    } catch (e) {
      console.log("[Lumio] onShown 动态菜单失败:", e);
    }
  });
  console.log("[Lumio] contextMenus.onShown 已注册");
} else {
  console.log("[Lumio] contextMenus.onShown 不支持，跳过动态菜单");
}

// ── 右键菜单点击 ──────────────────────────────────────────────────────

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id) return;

  const menuItemId = String(info.menuItemId);
  const isDetailPage = isDetailPageUrl(tab.url || "");

  // ★ 上下文感知：仅在详情页 page/image/video 项尝试提取元数据
  // 博主主页 / 链接 / 非详情页 → 跳过提取，直接构建载荷（节省 1.5s 超时）
  // ★ 提取失败不阻塞：buildCapturePayload 会 fallback 到发 URL，由后端再提取
  //   （硬性阻止会导致 YouTube/X/B站等平台因 1500ms 超时全部失败）
  let pageMeta: PageMeta | null = null;
  const needsMeta =
    isDetailPage &&
    (menuItemId === "lumio-capture-page" ||
      menuItemId === "lumio-capture-image" ||
      menuItemId === "lumio-capture-video");

  if (needsMeta) {
    pageMeta = await extractPageMeta(tab.id);
    if (!pageMeta) {
      console.log("Lumio: 元数据提取失败，fallback 到发 URL 由后端处理");
    }
  }

  // ★ 多图场景（IG 轮播帖 / X 多图推文 / 小红书多图笔记）：
  // 走 sendToLumioFromPageMeta 拆分，每个媒体独立发送为 InboxItem
  // 否则 buildCapturePayload 只发单条（direct_url=media_items[0]），丢失其余图
  if (pageMeta && pageMeta.media_items && pageMeta.media_items.length > 1) {
    await sendToLumioFromPageMeta(pageMeta, tab);
    return;
  }

  const payload = buildCapturePayload(menuItemId, info, tab, pageMeta);
  if (!payload) return;

  await sendToLumio(payload);
});

// ── 接收 popup / content 消息 ─────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (typeof msg !== "object" || msg === null) return false;

  const { type } = msg as { type?: string };

  if (type === "capture") {
    const data = (msg as { data: Partial<PageMeta> }).data;
    // ★ 提取失败停止发送：详情页必须有元数据
    // 但 X 视频推文 media_items 为空（blob: 无法提取），只要有 thumbnail 就允许发送
    const tabUrl = data.url || sender.tab?.url || "";
    const isDetail = isDetailPageUrl(tabUrl);
    if (isDetail && !data.media_items?.length && !data.thumbnail && !data.direct_url) {
      sendResponse({
        success: false,
        error: "页面元数据提取失败，请刷新页面后重试",
      });
      return false;
    }
    sendToLumioFromPageMeta(data, sender.tab).then(sendResponse);
    return true; // async
  }

  if (type === "getStatus") {
    sendResponse({ connected });
    return false;
  }

  if (type === "getSettings") {
    getSettings().then(sendResponse);
    return true;
  }

  if (type === "setSettings") {
    const patch = (msg as { settings: Partial<LumioSettings> }).settings;
    saveSettings(patch).then((next) => {
      client.updateBaseUrl(next.apiBaseUrl);
      sendResponse(next);
      checkHealth(); // 设置变更后立即重检
    });
    return true;
  }

  // 阶段 2：popup 请求从 content.js 提取元数据
  if (type === "extractPageMeta") {
    const tabId = (msg as { tabId?: number }).tabId;
    if (!tabId) {
      sendResponse(null);
      return false;
    }
    extractPageMeta(tabId).then(sendResponse);
    return true;
  }

  // ★ CSP 修复：content script 请求在主世界读取 window.__INITIAL_STATE__
  // 小红书 CSP 禁止 inline script，改用 chrome.scripting.executeScript({ world: "MAIN" })
  // 这是 MV3 标准做法，绕过 CSP 限制（scripting 权限已在 manifest 声明）
  //
  // ★ 卡死修复：原版返回整个 __INITIAL_STATE__（可能几 MB），序列化阻塞页面。
  // 改为在主世界内裁剪，只返回 noteDetailMap 首个 entry，大幅减少数据量。
  if (type === "xhs-read-state") {
    const tabId = sender.tab?.id;
    if (!tabId) {
      sendResponse(null);
      return false;
    }
    chrome.scripting
      .executeScript({
        target: { tabId },
        world: "MAIN",
        func: () => {
          const s = (window as unknown as {
            __INITIAL_STATE__?: {
              note?: {
                noteDetailMap?: Record<string, unknown>;
                noteMap?: Record<string, unknown>;
              };
            };
          }).__INITIAL_STATE__;
          if (!s) return null;
          // 裁剪：只返回 noteDetailMap 首个 entry，避免序列化整个 state
          const map = s.note?.noteDetailMap || s.note?.noteMap;
          if (!map) return { topKeys: Object.keys(s), noteKeys: s.note ? Object.keys(s.note) : [] };
          const keys = Object.keys(map);
          if (keys.length === 0) return { noteMapEmpty: true };
          return {
            note: {
              noteDetailMap: { [keys[0]]: map[keys[0]] },
            },
            _debug: {
              totalKeys: keys.length,
              firstKey: keys[0],
            },
          };
        },
      })
      .then((results) => {
        sendResponse(results?.[0]?.result || null);
      })
      .catch((e) => {
        console.log("[Lumio] xhs-read-state executeScript 失败:", e);
        sendResponse(null);
      });
    return true;
  }

  // 阶段 2：历史记录管理
  if (type === "getHistory") {
    const limit = (msg as { limit?: number }).limit ?? 50;
    getRecentHistory(limit).then(sendResponse);
    return true;
  }

  if (type === "getHistoryCount") {
    getHistoryCount().then(sendResponse);
    return true;
  }

  if (type === "deleteHistoryItem") {
    const id = (msg as { id?: string }).id;
    if (id) {
      deleteHistoryItem(id).then(() => sendResponse({ success: true }));
      return true;
    }
    sendResponse({ success: false, error: "missing id" });
    return false;
  }

  if (type === "deleteHistoryItems") {
    const ids = (msg as { ids?: string[] }).ids || [];
    deleteHistoryItems(ids).then(() => sendResponse({ success: true }));
    return true;
  }

  if (type === "clearHistory") {
    clearHistory().then(() => sendResponse({ success: true }));
    return true;
  }

  if (type === "resendHistoryItem") {
    const id = (msg as { id?: string }).id;
    if (id) {
      resendHistoryItem(id).then(sendResponse);
      return true;
    }
    sendResponse({ success: false, error: "missing id" });
    return false;
  }

  return false;
});

/** 重发历史记录 */
async function resendHistoryItem(id: string): Promise<CaptureResult> {
  const item = await getHistoryItem(id);
  if (!item) return { success: false, error: "记录不存在" };

  const payload: CapturePayload = {
    url: item.url,
    title: item.title,
    author: item.author,
    platform: item.platform,
    thumbnail: item.thumbnail,
    duration: item.duration,
    source: "browser",
    type: item.type,
    direct_url: item.direct_url,
  };
  return sendToLumio(payload);
}

// ── 发送到 Lumio API ─────────────────────────────────────────────────

/**
 * 从 PageMeta（可能含 media_items）构建并发送
 * - 多媒体场景（IG 轮播帖）：循环发送每个 media_item 作为独立 InboxItem
 *   每个 item 的 url 加 #media-{index} 后缀避免 unique 约束冲突
 * - 单媒体场景：media_items[0] → direct_url
 */
async function sendToLumioFromPageMeta(
  data: Partial<PageMeta>,
  tab: chrome.tabs.Tab | undefined,
): Promise<CaptureResult> {
  await settingsReady; // 确保 settings 已加载（MV3 SW 重启后端口可能未加载）
  const url = data.url || tab?.url || "";
  const baseMeta = {
    title: data.title || tab?.title || "",
    author: data.author || extractAuthorFromUrl(url),
    platform: data.platform || detectPlatform(url),
    thumbnail: data.thumbnail || "",
    duration: data.duration ?? null,
  };

  // 多媒体场景（IG 轮播帖 / X 多图推文 / 小红书多图笔记）
  // 每个媒体单独发送为独立 InboxItem，每个任务有自己的缩略图
  if (data.media_items && data.media_items.length > 1) {
    const results: CaptureResult[] = [];
    for (let i = 0; i < data.media_items.length; i++) {
      const item = data.media_items[i];
      const itemUrl = `${url}#media-${i + 1}`;
      // ★ 每个任务缩略图正确：
      // - 图片类型：用媒体自身的 URL 作为缩略图（inbox 预览直接显示）
      // - 视频类型：用帖子主缩略图（视频无法直接预览）
      const itemThumbnail = item.is_video
        ? (baseMeta.thumbnail || "")
        : item.url;
      const payload: CapturePayload = {
        url: itemUrl,
        ...baseMeta,
        thumbnail: itemThumbnail,
        source: "browser",
        type: item.is_video ? "video" : "image",
        direct_url: item.url,
      };
      const result = await client.capture(payload);
      results.push(result);
    }
    const last = results[results.length - 1] || { success: true, count: results.length };
    // 写入历史
    if (last.success) {
      await saveToHistory({ ...baseMeta, url, source: "browser", type: "url" } as PageMeta, last);
    }
    return last;
  }

  // 单媒体场景
  let directUrl = data.direct_url || "";
  let type = data.type || "url";
  let singleThumbnail = baseMeta.thumbnail;
  if (data.media_items && data.media_items.length > 0) {
    directUrl = data.media_items[0].url;
    type = data.media_items[0].is_video ? "video" : "image";
    // ★ 单媒体也修正缩略图：图片类型用自身 URL
    if (!data.media_items[0].is_video) {
      singleThumbnail = data.media_items[0].url;
    }
  }

  const payload: CapturePayload = {
    url,
    ...baseMeta,
    thumbnail: singleThumbnail,
    source: "browser",
    type,
    direct_url: directUrl,
  };

  const result = await client.capture(payload);
  if (result.success) {
    await saveToHistory({ ...baseMeta, url, source: "browser", type, thumbnail: singleThumbnail } as PageMeta, result);
  }
  return result;
}

/** 右键菜单专用：从 CapturePayload 直接发送（不走 media_items 拆分） */
async function sendToLumio(payload: CapturePayload): Promise<CaptureResult> {
  await settingsReady; // 确保 settings 已加载（MV3 SW 重启后端口可能未加载）
  const result = await client.capture(payload);
  if (result.success) {
    await saveToHistory(
      {
        url: payload.url,
        title: payload.title,
        author: payload.author,
        platform: payload.platform,
        thumbnail: payload.thumbnail,
        duration: payload.duration,
        source: "browser",
        type: payload.type,
      },
      result,
    );
  }
  return result;
}

// ── 阶段 2：从 content.js 提取页面元数据 ──────────────────────────────

async function extractPageMeta(tabId: number): Promise<PageMeta | null> {
  // 所有平台：调 content.js 的 extractNow（IG 已改为常驻 content script）
  // ★ 超时策略：
  //   - 小红书/IG：15000ms（readInitialState + DOM 兜底 + /embed/ fetch 慢）
  //   - YouTube/X/B站等：8000ms（waitForSelector 最多 3000ms + 余量）
  //   旧值 1500ms 会导致 YouTube waitForSelector 没跑完就超时
  try {
    const tab = await chrome.tabs.get(tabId);
    const url = tab.url || "";
    const needsLongTimeout =
      url.includes("xiaohongshu.com") || url.includes("instagram.com");
    const timeout = needsLongTimeout ? 15000 : 8000;
    let meta = await safeTabsMessage<PageMeta>(tabId, { type: "extractNow" }, timeout);
    if (meta && meta.url) return meta;

    // ★ sendMessage 失败兜底：content script 未注入（页面在插件更新前已打开）
    // 用 chrome.scripting.executeScript 手动注入 content script bundle，再重试一次
    // 这是 MV3 标准做法，解决"Receiving end does not exist"问题
    console.log("[Lumio] extractNow 未响应，尝试手动注入 content script");
    await injectContentScript(tabId);
    meta = await safeTabsMessage<PageMeta>(tabId, { type: "extractNow" }, timeout);
    if (meta && meta.url) return meta;
  } catch {
    // tab 查询失败，回退默认超时
    const meta = await safeTabsMessage<PageMeta>(tabId, { type: "extractNow" }, 8000);
    if (meta && meta.url) return meta;
  }
  return null;
}

/**
 * 手动注入 content script（兜底：页面在插件更新/重载前已打开，content script 未注入）
 * 从 manifest 动态读取 content_scripts.js 路径，避免硬编码 hash 文件名
 */
async function injectContentScript(tabId: number): Promise<void> {
  try {
    const manifest = chrome.runtime.getManifest();
    const files = manifest.content_scripts?.[0]?.js || [];
    if (files.length === 0) {
      console.log("[Lumio] manifest 无 content_scripts.js 配置");
      return;
    }
    await chrome.scripting.executeScript({
      target: { tabId },
      files,
    });
    // 等待 content script 初始化
    await new Promise((r) => setTimeout(r, 300));
  } catch (e) {
    console.log("[Lumio] 手动注入 content script 失败:", e);
  }
}

// ── 阶段 3：快捷键 commands ───────────────────────────────────────────

chrome.commands?.onCommand.addListener(async (command) => {
  if (command === "capture-page-silent") {
    // 静默发送当前页面到 Lumio
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id || !tab.url) return;

      const pageMeta = await extractPageMeta(tab.id);
      const isDetail = isDetailPageUrl(tab.url);
      if (isDetail && !pageMeta) {
        console.log("Lumio: 静默发送 - 提取失败，跳过");
        return;
      }
      await sendToLumioFromPageMeta(pageMeta || { url: tab.url, title: tab.title || "" }, tab);
    } catch (e) {
      console.log("Lumio: 静默发送失败", e);
    }
  }
});

// ── 阶段 3：Omnibox 地址栏 ────────────────────────────────────────────

/**
 * 从 URL 抓取 HTML 提取 og:image / twitter:image 作为缩略图
 * 用于 omnibox 模式下补全封面（无 content script 可用）
 *
 * ★ 核心策略：不限制 head 区域，直接在整个 HTML 中用 indexOf 快速定位
 *   原因：X 等 SPA 平台 HTML 可达 276KB，head 可能未正确闭合或
 *   og:image 在 head 很后面（被内联 JS 推后），限制 head 会漏掉
 *
 * ★ 限制：依赖 host_permissions，部分平台需 cookie 才能拿完整页面
 *    失败时返回空字符串，不影响发送
 */
async function fetchOgImage(url: string): Promise<{ thumbnail: string; title: string }> {
  try {
    console.log("Lumio: fetchOgImage 开始抓取", url);
    const resp = await fetch(url, {
      signal: AbortSignal.timeout(8000),
      credentials: "include",
      redirect: "follow",
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
      },
    });
    console.log("Lumio: fetchOgImage 响应", resp.status, resp.headers.get("content-type"));
    if (!resp.ok) {
      console.log("Lumio: fetchOgImage 失败 - HTTP", resp.status);
      return { thumbnail: "", title: "" };
    }
    const ct = resp.headers.get("content-type") || "";
    if (!ct.includes("text/html") && !ct.includes("application/xhtml")) {
      console.log("Lumio: fetchOgImage 跳过 - 非 HTML", ct);
      return { thumbnail: "", title: "" };
    }
    const html = await resp.text();
    console.log("Lumio: fetchOgImage HTML 长度", html.length);

    // 在整个 HTML 中提取 meta content（不限制 head）
    // 用 indexOf 快速定位 key，然后取周围 500 字符提取 content
    const extractMeta = (key: string, attr: "property" | "name"): string => {
      // 尝试两种引号
      const patterns = [
        `${attr}="${key}"`,
        `${attr}='${key}'`,
      ];
      for (const pat of patterns) {
        let idx = html.indexOf(pat);
        while (idx !== -1) {
          // 取 key 前后各 300 字符（meta 标签不会太长）
          const start = Math.max(0, idx - 300);
          const end = Math.min(html.length, idx + 300);
          const snippet = html.slice(start, end);

          // 在 snippet 中找 content="..." 或 content='...'
          // 同时确保这个 snippet 来自 <meta> 标签
          const metaStart = snippet.lastIndexOf("<meta", idx - start);
          if (metaStart === -1) {
            idx = html.indexOf(pat, idx + 1);
            continue;
          }
          const metaEnd = snippet.indexOf(">", idx - start);
          if (metaEnd === -1) {
            idx = html.indexOf(pat, idx + 1);
            continue;
          }
          const metaTag = snippet.slice(metaStart, metaEnd + 1);

          // 从 meta 标签中提取 content
          const cm =
            metaTag.match(/content\s*=\s*["']([^"']+)["']/i) ||
            metaTag.match(/content\s*=\s*([^\s"'>]+)/i);
          if (cm) {
            return decodeHtmlEntities(cm[1]);
          }
          idx = html.indexOf(pat, idx + 1);
        }
      }
      return "";
    };

    // og:image / twitter:image / og:image:secure_url
    const ogImg =
      extractMeta("og:image", "property") ||
      extractMeta("og:image:secure_url", "property") ||
      extractMeta("twitter:image", "name") ||
      extractMeta("twitter:image:src", "name") ||
      "";

    // og:title / twitter:title / <title>
    const ogTitle =
      extractMeta("og:title", "property") ||
      extractMeta("twitter:title", "name") ||
      html.match(/<title[^>]*>([^<]+)<\/title>/i)?.[1] ||
      "";

    console.log("Lumio: fetchOgImage 提取结果", {
      thumbnail: ogImg.slice(0, 100),
      title: ogTitle.slice(0, 100),
    });

    return {
      thumbnail: ogImg.trim(),
      title: decodeHtmlEntities(ogTitle).trim().slice(0, 200),
    };
  } catch (e) {
    console.log("Lumio: fetchOgImage 异常", e);
    return { thumbnail: "", title: "" };
  }
}

/** 解码常见 HTML 实体 */
function decodeHtmlEntities(s: string): string {
  return s
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#x2F;/g, "/")
    .replace(/&#47;/g, "/");
}

chrome.omnibox?.onInputEntered.addListener(async (text) => {
  const trimmed = text.trim();
  if (!trimmed) return;

  // 如果不是 URL，尝试加 https://
  let url = trimmed;
  if (!/^https?:\/\//.test(trimmed)) {
    if (/^[\w-]+(\.[\w-]+)+/.test(trimmed)) {
      url = `https://${trimmed}`;
    } else {
      console.log("Lumio: omnibox 输入不是有效 URL", trimmed);
      return;
    }
  }

  console.log("Lumio: omnibox 发送", url);

  // ★ 沿用 content script 提取（与右键/popup 同逻辑）
  // omnibox 触发时用户在地址栏输入，活动 tab 就是当前页面。
  // 如果活动 tab 域名与输入 URL 匹配，content script 已注入，
  // 直接调 extractPageMeta 拿完整元数据（含 thumbnail/media_items）。
  let pageMeta: PageMeta | null = null;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id && tab.url) {
      // 检查活动 tab 域名是否与输入 URL 相同（或同 hostname）
      const tabHost = new URL(tab.url).hostname;
      const inputHost = (() => {
        try { return new URL(url).hostname; } catch { return ""; }
      })();
      if (tabHost && inputHost && tabHost === inputHost) {
        console.log("Lumio: omnibox 沿用 content script 提取", tabHost);
        pageMeta = await extractPageMeta(tab.id);
      }
    }
  } catch (e) {
    console.log("Lumio: omnibox content script 提取失败", e);
  }

  // content script 提取失败 → 回退到 fetchOgImage
  let thumbnail = "";
  let title = "";
  if (pageMeta) {
    thumbnail = pageMeta.thumbnail || "";
    title = pageMeta.title || "";
  } else {
    const og = await fetchOgImage(url);
    thumbnail = og.thumbnail;
    title = og.title;
  }

  const payload: CapturePayload = {
    url,
    title,
    author: pageMeta?.author || extractAuthorFromUrl(url),
    platform: pageMeta?.platform || detectPlatform(url),
    thumbnail,
    duration: pageMeta?.duration ?? null,
    source: "browser",
    type: "url",
  };
  await sendToLumio(payload);
});

// omnibox 建议提示
chrome.omnibox?.onInputStarted.addListener(() => {
  chrome.omnibox.setDefaultSuggestion({
    description: "发送 URL 到 Lumio：输入完整网址后回车",
  });
});
