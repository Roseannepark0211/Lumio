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
import { createContextMenus, buildCapturePayload, safeTabsMessage } from "./contextMenus";
import { DEFAULT_SETTINGS, SETTINGS_KEY, getSettings, saveSettings } from "./settings";

// ── 客户端实例 ────────────────────────────────────────────────────────

let client = new LumioClient(DEFAULT_SETTINGS.apiBaseUrl);
let connected = false;

// 启动时加载设置
getSettings().then((settings) => {
  client.updateBaseUrl(settings.apiBaseUrl);
});

// ── 健康轮询 ──────────────────────────────────────────────────────────

async function checkHealth() {
  connected = await client.health();
  chrome.runtime.sendMessage({ type: "status", connected }).catch(() => {});
}

setInterval(checkHealth, 5000);
checkHealth();

// ── 安装时创建右键菜单 ────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  createContextMenus();
});

// ── 右键菜单点击 ──────────────────────────────────────────────────────

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id) return;

  // 阶段 1：先不调 content.js（content scripts 还没注入）
  // 阶段 2 会改为：先尝试从 content.js 拿 pageMeta
  const pageMeta: PageMeta | null = null;

  const payload = buildCapturePayload(String(info.menuItemId), info, tab, pageMeta);
  if (!payload) return;

  const result = await sendToLumio(payload);
  notifyUser(result, payload);
});

// ── 接收 popup / content 消息 ─────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (typeof msg !== "object" || msg === null) return false;

  const { type } = msg as { type?: string };

  if (type === "capture") {
    const data = (msg as { data: Partial<PageMeta> }).data;
    sendToLumio(buildPayloadFromPartial(data, sender.tab)).then(sendResponse);
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

  return false;
});

// ── 发送到 Lumio API ─────────────────────────────────────────────────

function buildPayloadFromPartial(
  data: Partial<PageMeta>,
  tab: chrome.tabs.Tab | undefined,
): CapturePayload {
  const url = data.url || tab?.url || "";
  return {
    url,
    title: data.title || tab?.title || "",
    author: data.author || extractAuthorFromUrl(url),
    platform: data.platform || detectPlatform(url),
    thumbnail: data.thumbnail || "",
    duration: data.duration ?? null,
    source: "browser",
    type: data.type || "url",
    direct_url: data.direct_url,
  };
}

async function sendToLumio(payload: CapturePayload): Promise<CaptureResult> {
  const result = await client.capture(payload);
  // 阶段 2 会加：成功后 saveToLocalHistory
  return result;
}

// ── 通知反馈 ──────────────────────────────────────────────────────────

function notifyUser(result: CaptureResult, payload: CapturePayload) {
  const ok = result.success;
  const iconUrl = chrome.runtime.getURL("src/assets/icons/logo-48.png");
  if (ok) {
    const titleStr = payload.title ? `：${payload.title.slice(0, 40)}` : "";
    chrome.notifications.create({
      type: "basic",
      iconUrl,
      title: "Lumio ✓",
      message: `已发送到 Inbox${titleStr}`,
      priority: 0,
    });
  } else {
    chrome.notifications.create({
      type: "basic",
      iconUrl,
      title: "Lumio ✗",
      message: `发送失败：${result.error || "未知错误"}`,
      priority: 2,
    });
  }
}

// ── 阶段 2 占位：从 content.js 提取页面元数据 ─────────────────────────

export async function extractPageMeta(tabId: number): Promise<PageMeta | null> {
  // 阶段 2 实现：尝试 chrome.tabs.sendMessage(tabId, { type: "extractNow" })
  // 阶段 2 实现：IG 页面 fallback 到 chrome.scripting.executeScript({ files: ["ig_extract.js"] })
  void tabId;
  void safeTabsMessage; // 阶段 2 用
  return null;
}

// 导出供阶段 2 使用
export { client, saveSettings, getSettings, SETTINGS_KEY };
