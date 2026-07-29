/**
 * Lumio Content Script 主入口
 *
 * 注入：YouTube / Instagram / X / B站 / 快手 / 小红书
 *
 * 职责：
 * 1. 页面加载后提取元数据 → 推送给 popup（如果打开）
 * 2. 响应 popup 的 extractNow 请求 → 返回最新元数据
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

  if (type === "extractNow") {
    extract().then((fresh) => sendResponse(fresh));
    return true; // async
  }

  // 诊断采集：popup 触发，采集当前页 DOM/State 元信息返回 JSON
  if (type === "diagnose") {
    diagnose().then((report) => sendResponse(report));
    return true; // async
  }

  return false;
});
