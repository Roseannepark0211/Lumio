/**
 * 平台 badge 颜色映射 + 标签
 */
import type { Platform } from "../../types";

/** 短标签（卡片角标用） */
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

/** 长标签（预览面板等空间较大的场景用） */
export const PLATFORM_LABELS_FULL: Record<Platform, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
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
