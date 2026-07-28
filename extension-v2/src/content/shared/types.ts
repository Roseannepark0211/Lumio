/**
 * Content script 内部提取结果类型
 */
import type { PageMeta, Platform, MediaItem, MediaType } from "../../types";

export interface ExtractResult {
  url: string;
  title: string;
  author: string;
  platform: Platform;
  thumbnail: string;
  duration: number | null;
  type?: MediaType;
  media_items?: MediaItem[];
  direct_url?: string;
}

export function toPageMeta(r: ExtractResult): PageMeta {
  return {
    url: r.url,
    title: r.title,
    author: r.author,
    platform: r.platform,
    thumbnail: r.thumbnail,
    duration: r.duration,
    source: "browser",
    type: r.type || "url",
    media_items: r.media_items,
    direct_url: r.direct_url,
  };
}
