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

// 带超时的 sendMessage，防止 content.js 未响应时右键发送 hang 住
async function safeTabsMessage(tabId, message, timeoutMs = 1500) {
  try {
    const result = await Promise.race([
      chrome.tabs.sendMessage(tabId, message),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("sendMessage timeout")), timeoutMs)
      ),
    ]);
    return result;
  } catch {
    return null;
  }
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  // 先尝试从 content.js 拿到当前页面的完整元数据（支持的平台才有）
  let pageMeta = null;
  if (tab && tab.id) {
    pageMeta = await safeTabsMessage(tab.id, { type: "extractNow" });
  }

  let payload = null;

  switch (info.menuItemId) {
    case "lumio-capture-page":
      // 发送当前页面：优先用 content.js 提取的元数据，否则仅发 URL
      if (pageMeta && !pageMeta.error && pageMeta.url) {
        payload = {
          url: pageMeta.url || tab.url,
          title: pageMeta.title || tab.title || "",
          author: pageMeta.author || "",
          platform: pageMeta.platform || detectPlatform(tab.url),
          thumbnail: pageMeta.thumbnail || "",
          duration: pageMeta.duration || null,
          source: "browser",
          type: "url",
        };
        break;
      }

      // IG 详情页：content.js 不注入（防自动化检测），改走 ig_extract.js 一次性提取
      // 之前这里只发裸 URL，后端需 cookie 调 IG API → 无 cookie 必失败
      if (tab && tab.url && tab.url.includes("instagram.com") &&
          (tab.url.includes("/p/") || tab.url.includes("/reel/"))) {
        try {
          const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ["ig_extract.js"],
          });
          if (results && results[0] && results[0].result) {
            await sendToLumio(results[0].result);
            return;
          }
        } catch (e) {
          console.log("IG page extract failed, falling back to URL:", e);
        }
      }

      // content.js 未注入/超时/非详情页 → 仅发页面 URL
      payload = { url: tab.url, title: tab.title || "", source: "browser", type: "url" };
      break;

    case "lumio-capture-link":
      // 发送链接：用 linkUrl 而非页面 URL
      payload = {
        url: info.linkUrl,
        title: info.selectionText || info.linkUrl,
        source: "browser",
        type: "url",
      };
      break;

    case "lumio-capture-video":
    case "lumio-capture-image": {
      const isVideo = info.menuItemId === "lumio-capture-video";
      const srcUrl = info.srcUrl || "";

      // 情况 A：当前页是支持的平台（YouTube/X/B站/快手/小红书）
      // → 发送页面 URL + 元数据，让 Lumio 通过 Provider 系统解析（支持格式选择 + 正确鉴权）
      if (pageMeta && !pageMeta.error && pageMeta.url && pageMeta.platform) {
        payload = {
          url: pageMeta.url || tab.url,
          title: pageMeta.title || tab.title || "",
          author: pageMeta.author || "",
          platform: pageMeta.platform,
          thumbnail: pageMeta.thumbnail || "",
          duration: pageMeta.duration || null,
          source: "browser",
          type: isVideo ? "video" : "image",
          // 不传 direct_url —— 让 Lumio 走 Provider 系统解析，避免 CDN 直链 403
        };
        break;
      }

      // 情况 B：IG 页面 → 一次性注入 ig_extract.js 提取直链
      if (tab && tab.url && tab.url.includes("instagram.com") &&
          (tab.url.includes("/p/") || tab.url.includes("/reel/"))) {
        try {
          const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ["ig_extract.js"],
          });
          if (results && results[0] && results[0].result) {
            await sendToLumio(results[0].result);
            return;
          }
        } catch (e) {
          console.log("IG extract failed, falling back:", e);
        }
      }

      // 情况 C：非支持平台（如第三方网站的裸视频/图片）→ 用 srcUrl 作为 direct_url
      // 此时只能直链下载，无法走 Provider 格式选择
      if (srcUrl) {
        payload = {
          url: tab ? tab.url : srcUrl,    // 页面 URL 用作 task.url（历史/去重）
          title: (isVideo ? (tab?.title || "Video") : (info.alt || tab?.title || "Image")),
          source: "browser",
          type: isVideo ? "video" : "image",
          direct_url: srcUrl,             // 实际下载用直链
        };
      }
      break;
    }
  }

  if (!payload || !payload.url) return;
  const result = await sendToLumio(payload);
  // 右键发送后给用户视觉反馈
  notifyUser(result, payload);
});

// ── 通知反馈 ───────────────────────────────────────────────────────

function notifyUser(result, payload) {
  const ok = result && result.success;
  const iconUrl = chrome.runtime.getURL("icons/logo-48.png");
  if (ok) {
    const titleStr = payload.title ? `：${payload.title.slice(0, 40)}` : "";
    chrome.notifications.create({
      type: "basic",
      iconUrl: iconUrl,
      title: "Lumio ✓",
      message: `已发送到 Inbox${titleStr}`,
      priority: 0,
    });
  } else {
    chrome.notifications.create({
      type: "basic",
      iconUrl: iconUrl,
      title: "Lumio ✗",
      message: `发送失败：${(result && result.error) || "未知错误"}`,
      priority: 2,
    });
  }
}

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
  // 从 URL 补全 author（部分平台可从 URL 提取作者名）
  if (!data.author && data.url) {
    const urlAuthor = extractAuthorFromUrl(data.url);
    if (urlAuthor) data.author = urlAuthor;
  }
  // 补全 platform
  if (!data.platform && data.url) {
    data.platform = detectPlatform(data.url);
  }

  try {
    // 多媒体场景（IG 轮播帖）：循环发送每个 media_item 作为独立 InboxItem
    // 每个 item 的 url 加 #media-{index} 后缀避免 unique 约束冲突
    if (data.media_items && data.media_items.length > 1) {
      const results = [];
      for (let i = 0; i < data.media_items.length; i++) {
        const item = data.media_items[i];
        const itemUrl = `${data.url}#media-${i + 1}`;
        const resp = await fetch(`${API_BASE}/capture`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: itemUrl,
            title: data.title || "",
            author: data.author || "",
            platform: data.platform || detectPlatform(data.url),
            thumbnail: data.thumbnail || "",
            duration: data.duration || null,
            source: data.source || "browser",
            type: item.is_video ? "video" : "image",
            direct_url: item.url,
          })
        });
        results.push(await resp.json());
      }
      return results[results.length - 1] || { ok: true, count: results.length };
    }

    // 单媒体场景：media_items[0] → direct_url
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
  if (url.includes("bilibili.com") || url.includes("b23.tv")) return "bilibili";
  if (url.includes("kuaishou.com")) return "kuaishou";
  if (url.includes("xiaohongshu.com") || url.includes("xhslink.com") || url.includes("xhslink.cn")) return "xiaohongshu";
  return "";
}

function extractAuthorFromUrl(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    const host = u.hostname;

    // Instagram: instagram.com/{username}/p/... or /reel/...
    // 注意：instagram.com/p/{id}/ 或 /reel/{id}/ 时 parts[0] 是 "p"/"reel"，不是作者
    // 只有 instagram.com/{username}/p/{id}/ 才有作者
    if (host.includes("instagram.com") && parts.length >= 1) {
      const igReserved = ["p", "reel", "tv", "explore", "accounts", "direct", "stories"];
      if (!igReserved.includes(parts[0]) && parts[0] !== "") {
        return parts[0];
      }
      return "";
    }
    // X: x.com/{username}/status/...
    if ((host.includes("x.com") || host.includes("twitter.com")) && parts.length >= 1) {
      return parts[0];
    }
    // YouTube: youtube.com/@{channel} or /channel/{id} or /c/{name}
    if (host.includes("youtube.com")) {
      if (parts[0] && parts[0].startsWith("@")) return parts[0].slice(1);
      if (parts[0] === "channel" || parts[0] === "c" || parts[0] === "user") return parts[1] || "";
    }
    // B站: bilibili.com/space/{uid} 或 /video/BV...（视频页无法从 URL 拿作者）
    if (host.includes("bilibili.com")) {
      if (parts[0] === "space") return parts[1] || "";
      return "";
    }
    // 快手: kuaishou.com/profile/{uid}
    if (host.includes("kuaishou.com")) {
      if (parts[0] === "profile") return parts[1] || "";
      return "";
    }
    // 小红书: xiaohongshu.com/user/profile/{uid}
    if (host.includes("xiaohongshu.com")) {
      if (parts[0] === "user" && parts[1] === "profile") return parts[2] || "";
      return "";
    }
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
