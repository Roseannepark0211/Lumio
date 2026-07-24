/* ── Lumio Popup Script ── */

const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const btnSend = document.getElementById("btnSend");
const msgDiv = document.getElementById("msg");
const historyDiv = document.getElementById("history");

let connected = false;
let pageInfo = null;

// ── 连接状态 ───────────────────────────────────────────────────────

chrome.runtime.sendMessage({ type: "getStatus" }, (resp) => {
  if (resp) updateStatus(resp.connected);
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "status") updateStatus(msg.connected);
  if (msg.type === "pageInfo") pageInfo = msg.data;
});

function updateStatus(ok) {
  connected = ok;
  statusDot.className = "status-dot " + (ok ? "on" : "off");
  statusText.textContent = ok ? "已连接" : "未连接";
  btnSend.disabled = !ok;
}

// ── 发送当前页面 ───────────────────────────────────────────────────

btnSend.addEventListener("click", async () => {
  // 先从 content.js 获取最新页面信息
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  let data = pageInfo;
  try {
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "extractNow" });
    if (resp && !resp.error) data = resp;
  } catch {}

  // IG 详情页：content.js 不注入（防自动化检测），改走 ig_extract.js 一次性提取
  // 否则 data 会 fallback 到裸 URL，后端无 cookie 调 IG API 必失败
  if (tab.url && tab.url.includes("instagram.com") &&
      (tab.url.includes("/p/") || tab.url.includes("/reel/"))) {
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["ig_extract.js"],
      });
      if (results && results[0] && results[0].result) {
        data = results[0].result;
      }
    } catch (e) {
      console.log("popup IG extract failed:", e);
    }
  }

  if (!data || !data.url) {
    // fallback: 直接用 tab URL
    data = { url: tab.url, title: tab.title, source: "browser" };
  }

  btnSend.disabled = true;
  btnSend.textContent = "发送中...";

  chrome.runtime.sendMessage({ type: "capture", data }, (result) => {
    btnSend.disabled = false;
    btnSend.textContent = "发送当前页面到 Lumio";
    if (result && result.success) {
      showMsg("已发送 ✓", "ok");
      loadHistory();
    } else {
      showMsg(result?.error || "发送失败", "err");
    }
  });
});

// ── 消息提示 ───────────────────────────────────────────────────────

function showMsg(text, type) {
  msgDiv.textContent = text;
  msgDiv.className = "msg " + type;
  setTimeout(() => { msgDiv.className = "msg"; }, 2000);
}

// ── 历史记录 ───────────────────────────────────────────────────────

async function loadHistory() {
  const { history = [] } = await chrome.storage.local.get("history");
  if (history.length === 0) {
    historyDiv.innerHTML = '<div class="empty">暂无记录</div>';
    return;
  }
  historyDiv.innerHTML = history.slice(0, 20).map(item => {
    const time = new Date(item.time).toLocaleString("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
    });
    const platform = item.platform ? `[${item.platform}] ` : "";
    return `<div class="history-item">
      <span class="time">${time}</span>
      <span class="title">${platform}${escHtml(item.title || item.url)}</span>
    </div>`;
  }).join("");
}

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

loadHistory();

// ── 清除历史 ──────────────────────────────────────────────────────

document.getElementById("btnClear").addEventListener("click", async () => {
  await chrome.storage.local.set({ history: [] });
  loadHistory();
});
