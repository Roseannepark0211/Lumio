/**
 * Lumio Extension 共享类型定义
 */

export type Platform =
  | "youtube"
  | "instagram"
  | "x"
  | "bilibili"
  | "kuaishou"
  | "xiaohongshu"
  | "";

export type MediaType = "url" | "video" | "image";

export interface MediaItem {
  url: string;
  is_video: boolean;
  width?: number;
  height?: number;
}

/** 从页面提取的元数据（content.js / ig_extract.js 返回） */
export interface PageMeta {
  url: string;
  title: string;
  author: string;
  platform: Platform;
  thumbnail: string;
  duration: number | null;
  source: "browser";
  type: MediaType;
  media_items?: MediaItem[];
  direct_url?: string;
}

/** 发送到 Lumio API 的载荷（简化版，去掉 media_items，由 background 处理） */
export interface CapturePayload {
  url: string;
  title: string;
  author: string;
  platform: Platform;
  thumbnail: string;
  duration: number | null;
  source: "browser";
  type: MediaType;
  direct_url?: string;
}

/** Lumio API 返回 */
export interface CaptureResult {
  success: boolean;
  inbox_id?: string;
  count?: number;
  error?: string;
}

/** 历史记录（IndexedDB） */
export interface HistoryItem extends PageMeta {
  id: string;
  time: number;
  inbox_id?: string;
  status?: "pending" | "downloading" | "done" | "error";
}

/** 插件设置 */
export interface LumioSettings {
  apiBaseUrl: string; // 默认 http://127.0.0.1:38900
  theme: "system" | "light" | "dark";
}
