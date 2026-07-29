/**
 * 平台标签共享数据
 *
 * ★ background（Service Worker）和 popup（React UI）是两个独立打包上下文，
 *   但都能 import 同一份源码模块（Vite 会分别打包）。
 *
 * ★ 抽到 shared/ 的目的：消除 contextMenus.ts 的 platformLabel 函数 与
 *   popup/components/platform-badge.ts 的 PLATFORM_LABELS_FULL 常量 之间的重复维护
 */
import type { Platform } from "../types";

/** 完整平台中文名（用于菜单标题、预览面板） */
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

/** 获取平台完整中文名（替代原 contextMenus.ts 的 platformLabel 函数） */
export function platformLabel(platform: Platform): string {
  return PLATFORM_LABELS_FULL[platform] || "";
}
