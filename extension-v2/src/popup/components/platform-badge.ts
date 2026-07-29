/**
 * 平台 badge 颜色映射 + 标签
 *
 * ★ 完整平台名（PLATFORM_LABELS_FULL）已抽到 ../../shared/platformLabels.ts，
 *   与 background 共用一份映射表，避免重复维护
 */
import type { Platform } from "../../types";
export { PLATFORM_LABELS_FULL } from "../../shared/platformLabels";

/** 短标签（卡片角标用，仅 popup UI 需要） */
export const PLATFORM_LABELS: Record<Platform, string> = {
  youtube: "YT",
  instagram: "IG",
  x: "X",
  bilibili: "B站",
  kuaishou: "快手",
  xiaohongshu: "小红书",
  douyin: "抖音",
  weibo: "微博",
  "": "",
};

export const PLATFORM_COLORS: Record<Platform, string> = {
  youtube: "bg-[#FF0000]",
  instagram: "bg-[#E1306C]",
  x: "bg-[#1DA1F2]",
  bilibili: "bg-[#FB7299]",
  kuaishou: "bg-[#FF6600]",
  xiaohongshu: "bg-[#FF2741]",
  douyin: "bg-[#000000]",
  weibo: "bg-[#E6162D]",
  "": "bg-text-muted",
};
