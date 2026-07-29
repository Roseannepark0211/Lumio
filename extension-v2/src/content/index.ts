/**
 * Lumio Content Script 主入口
 *
 * 注入：YouTube / Instagram / X / B站 / 快手 / 小红书
 *
 * 职责：
 * 1. 页面加载后提取元数据 → 推送给 popup（如果打开）
 * 2. 响应 popup 的 extractNow 请求 → 返回最新元数据
 * 3. ★ 阶段3：监听 SPA 路由变化 → URL 变化时通知 popup 重新提取
 *
 * ★ 区域限定原则：所有平台只提取主贴区域，不抓评论区/推荐区
 * ★ 懒提取原则：不在页面加载时主动提取 YouTube 元数据，
 *   避免频繁 DOM 查询触发 YouTube 反爬检测/人机验证。
 *   只在 popup 打开（extractNow 请求）或右键菜单时才提取。
 */
import type { PageMeta } from "../types";
import { detectPlatform } from "./shared/detector";
import { toPageMeta, type ExtractResult } from "./shared/types";
import { extractYouTube } from "./platforms/youtube";
import { extractInstagram } from "./ig_extract";
import { extractX } from "./platforms/x";
import { extractBilibili } from "./platforms/bilibili";
import { extractKuaishou } from "./platforms/kuaishou";
import { extractXiaohongshu } from "./platforms/xiaohongshu";
import { diagnose } from "./shared/diagnose";
import { isDetailPageUrl } from "../shared/detailPage";

async function extract(): Promise<PageMeta | null> {
  const platform = detectPlatform();
  if (!platform) return null;

  // 详情页：尝试提取详细元数据
  let detailed: ExtractResult | null = null;
  switch (platform) {
    case "youtube":
      detailed = await extractYouTube();
      break;
    case "instagram":
      detailed = await extractInstagram();
      break;
    case "x":
      detailed = extractX();
      break;
    case "bilibili":
      detailed = extractBilibili();
      break;
    case "kuaishou":
      detailed = extractKuaishou();
      break;
    case "xiaohongshu":
      detailed = await extractXiaohongshu();
      break;
  }

  if (detailed) return toPageMeta(detailed);

  // 非详情页（首页/用户主页/搜索页）：返回基本信息，让 Lumio 自行判断
  return {
    url: window.location.href,
    title: document.title || "",
    author: "",
    platform,
    thumbnail: "",
    duration: null,
    source: "browser",
    type: "url",
  };
}

// ★ 懒提取：只在 popup 打开时才提取（响应 extractNow 请求）
// 旧实现在页面加载时主动 extract() + sendMessage，每次访问 YouTube 视频页都触发，
// 频繁 DOM 查询（ytd-watch-metadata 等）会被 YouTube 检测为机器人行为 → 人机验证。
// 改为：popup 打开时由 popup 主动发 extractNow 消息，content script 才提取。
// 右键菜单走独立路径（contextMenus.ts → buildCapturePayload），不依赖此自动提取。
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (typeof msg !== "object" || msg === null) return false;
  const { type } = msg as { type?: string };
  console.log("[Lumio-content] 收到消息:", type);

  if (type === "extractNow") {
    extract().then((fresh) => {
      console.log("[Lumio-content] extract 完成:", fresh ? "有数据" : "空");
      sendResponse(fresh);
    });
    return true; // async
  }

  // 诊断采集：popup 触发，采集当前页 DOM/State 元信息返回 JSON
  if (type === "diagnose") {
    console.log("[Lumio-content] 开始诊断采集");
    diagnose().then((report) => {
      console.log("[Lumio-content] 诊断采集完成");
      sendResponse(report);
    });
    return true; // async
  }

  return false;
});

console.log("[Lumio-content] content script 已注入:", window.location.href);

// ── 阶段 3：SPA 路由监听 ─────────────────────────────────────────────
//
// 场景：用户在 IG/小红书博主主页（瀑布流）点击某个帖子 → 弹窗弹出 →
// URL 变成 /p/{id}/ 或 /explore/{id}（但页面不刷新，是 SPA 路由）。
//
// 问题：popup 打开时提取的是主页元数据（空），用户点击帖子后 popup 不会自动刷新。
//
// 方案：监听 SPA 路由变化（popstate + hook pushState/replaceState），
// URL 从非详情页变成详情页时，通知 popup 重新提取。
//
// ★ 为什么不直接在 content script 里提取后推送？
//   1. popup 可能没打开，sendMessage 会失败
//   2. 提取耗时（IG 12s），直接在路由变化时提取会拖慢页面
//   3. popup 打开时主动 extractNow 更可控（用户预期"打开 popup 看当前页"）
//
// ★ 所以只通知 popup "URL 变了"，由 popup 决定是否重新提取。

let lastUrl = window.location.href;
let lastWasDetail = isDetailPageUrl(lastUrl);

/**
 * URL 变化时的处理
 * - 非详情 → 详情：通知 popup "进入详情页"（popup 会重新提取）
 * - 详情 → 非详情：通知 popup "离开详情页"（popup 清空预览）
 * - 详情 → 详情（切换帖子）：通知 popup "切换帖子"（popup 重新提取）
 */
function onUrlChanged(): void {
  const newUrl = window.location.href;
  if (newUrl === lastUrl) return;

  const newIsDetail = isDetailPageUrl(newUrl);
  const transition =
    !lastWasDetail && newIsDetail
      ? "enter-detail"
      : lastWasDetail && !newIsDetail
        ? "leave-detail"
        : lastWasDetail && newIsDetail
          ? "switch-detail"
          : "navigate-non-detail";

  lastUrl = newUrl;
  lastWasDetail = newIsDetail;

  // 通知 popup（如果打开了）
  chrome.runtime
    .sendMessage({
      type: "urlChanged",
      url: newUrl,
      isDetail: newIsDetail,
      transition,
    })
    .catch(() => {
      // popup 未打开，忽略
    });
}

// 监听 popstate（浏览器前进/后退）
window.addEventListener("popstate", onUrlChanged);

// hook pushState / replaceState（SPA 内部路由跳转）
// ★ 必须在 content script 顶层执行一次，hook 原生方法
const originalPushState = history.pushState.bind(history);
const originalReplaceState = history.replaceState.bind(history);
history.pushState = function (...args: Parameters<typeof history.pushState>) {
  const result = originalPushState(...args);
  // 延迟通知，等 SPA 渲染完
  setTimeout(onUrlChanged, 100);
  return result;
};
history.replaceState = function (...args: Parameters<typeof history.replaceState>) {
  const result = originalReplaceState(...args);
  setTimeout(onUrlChanged, 100);
  return result;
};
