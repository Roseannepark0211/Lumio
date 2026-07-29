/**
 * 平台检测（content script 专用，基于 window.location.hostname）
 */
import type { Platform } from "../../types";

export function detectPlatform(): Platform {
  const hostname = window.location.hostname;
  if (hostname.includes("youtube.com") || hostname.includes("youtu.be")) return "youtube";
  if (hostname.includes("instagram.com")) return "instagram";
  if (hostname.includes("x.com") || hostname.includes("twitter.com")) return "x";
  if (hostname.includes("bilibili.com") || hostname.includes("b23.tv")) return "bilibili";
  if (hostname.includes("kuaishou.com")) return "kuaishou";
  if (hostname.includes("xiaohongshu.com")) return "xiaohongshu";
  return "";
}
