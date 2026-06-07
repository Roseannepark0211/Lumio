/* ── Lumio Extension Background (Service Worker) ── */

const API_BASE = "http://127.0.0.1:38900";  // 默认端口，与 Lumio config api_port 一致

// ── Health polling ──────────────────────────────────────────────────

let connected = false;

async function checkHealth() {
  try {
    const resp = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
    connected = resp.ok;
  } catch {
    connected = false;
  }
  // 广播连接状态给 popup
  chrome.runtime.sendMessage({ type: "status", connected }).catch(() => {});
}

// 每 5 秒检查一次
setInterval(checkHealth, 5000);
checkHealth();

// ── 安装时创建右键菜单 ─────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "lumio-capture-page",
    title: "发送当前页面到 Lumio",
    contexts: ["page"]
  });
  chrome.contextMenus.create({
    id: "lumio-capture-link",
    title: "发送链接到 Lumio",
    contexts: ["link"]
  });
  chrome.contextMenus.create({
    id: "lumio-capture-video",
    title: "发送视频到 Lumio",
    contexts: ["video"]
  });
  chrome.contextMenus.create({
    id: "lumio-capture-image",
    title: "发送图片到 Lumio",
    contexts: ["image"]
  });
});

// ── 右键菜单点击 ───────────────────────────────────────────────────

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  let url = "";
  let title = "";

  switch (info.menuItemId) {
    case "lumio-capture-page":
      url = tab.url;
      title = tab.title;
      break;
    case "lumio-capture-link":
      url = info.linkUrl;
      title = info.selectionText || info.linkUrl;
      break;
    case "lumio-capture-video":
      url = info.srcUrl;
      title = tab.title || "Video";
      break;
    case "lumio-capture-image":
      url = info.srcUrl || info.pageUrl;
      title = info.alt || tab.title || "Image";
      break;
  }

  if (!url) return;

  // IG 页面：一次性注入提取脚本，获取媒体直链
  if (url.includes("instagram.com") && (url.includes("/p/") || url.includes("/reel/"))) {
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["ig_extract.js"],
      });
      if (results && results[0] && results[0].result) {
        const data = results[0].result;
        await sendToLumio(data);
        return;
      }
    } catch (e) {
      console.log("IG extract failed, falling back to URL:", e);
    }
  }

  await sendToLumio({ url, title, source: "browser" });
});

// ── 接收 content.js 消息 ───────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "capture") {
    sendToLumio(msg.data).then(sendResponse);
    return true; // async response
  }
  if (msg.type === "getStatus") {
    sendResponse({ connected });
    return false;
  }
});

// ── 发送到 Lumio API ───────────────────────────────────────────────

async function sendToLumio(data) {
  // 从 URL 补全 author（IG content script 已移除，需要从 URL 提取）
  if (!data.author && data.url) {
    const urlAuthor = extractAuthorFromUrl(data.url);
    if (urlAuthor) data.author = urlAuthor;
  }
  if (!data.platform && data.url) {
    data.platform = detectPlatform(data.url);
  }
  try {
    // IG 一次性提取结果：media_items → direct_url
    let directUrl = data.direct_url || "";
    let type = data.type || "url";
    if (data.media_items && data.media_items.length > 0) {
      directUrl = data.media_items[0].url;
      type = data.media_items[0].is_video ? "video" : "image";
    }

    const resp = await fetch(`${API_BASE}/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: data.url,
        title: data.title || "",
        author: data.author || "",
        platform: data.platform || detectPlatform(data.url),
        thumbnail: data.thumbnail || "",
        duration: data.duration || null,
        source: data.source || "browser",
        type: type,
        direct_url: directUrl,
      })
    });
    const result = await resp.json();
    // 记录到本地历史
    if (result.success) {
      saveToLocalHistory({ ...data, inbox_id: result.inbox_id, time: Date.now() });
    }
    return result;
  } catch (err) {
    return { success: false, error: err.message };
  }
}

// ── 平台检测 ───────────────────────────────────────────────────────

function detectPlatform(url) {
  if (!url) return "";
  if (url.includes("youtube.com") || url.includes("youtu.be")) return "youtube";
  if (url.includes("instagram.com")) return "instagram";
  if (url.includes("x.com") || url.includes("twitter.com")) return "x";
  return "";
}

function extractAuthorFromUrl(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    // Instagram: instagram.com/{username}/p/... or /reel/...
    if (u.hostname.includes("instagram.com") && parts.length >= 1) {
      return parts[0];
    }
    // X: x.com/{username}/status/...
    if ((u.hostname.includes("x.com") || u.hostname.includes("twitter.com")) && parts.length >= 1) {
      return parts[0];
    }
    // YouTube: 从页面 title 提取（右键时 tab.title 已包含频道名）
  } catch {}
  return "";
}

// ── 本地历史（chrome.storage.local）───────────────────────────────

async function saveToLocalHistory(item) {
  const { history = [] } = await chrome.storage.local.get("history");
  history.unshift(item);
  // 只保留最近 50 条
  if (history.length > 50) history.length = 50;
  await chrome.storage.local.set({ history });
}
