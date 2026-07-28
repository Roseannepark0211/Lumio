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

// 页面加载后立即提取并推送（popup 打开时能收到）
extract().then((data) => {
  if (data) {
    chrome.runtime.sendMessage({ type: "pageInfo", data }).catch(() => {});
  }
});

// 响应 popup 的 extractNow 请求
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (typeof msg === "object" && msg !== null && (msg as { type?: string }).type === "extractNow") {
    extract().then((fresh) => sendResponse(fresh));
    return true; // async
  }
  return false;
});
