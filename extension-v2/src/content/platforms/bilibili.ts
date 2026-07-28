/**
 * B站元数据提取
 * - 仅在 /video/BV... 或 /video/av... 页提取
 * - author 从 meta[itemprop] / .up-name / __INITIAL_STATE__.upData.name 多路径兜底
 * - duration 从 __INITIAL_STATE__.videoData.duration 提取
 */
import { meta } from "../shared/og";
import type { ExtractResult } from "../shared/types";

interface BilibiliInitialState {
  upData?: { name?: string };
  videoData?: { duration?: number | string };
}

export function extractBilibili(): ExtractResult | null {
  const url = window.location.href;
  if (!/\/video\/(BV|av)/i.test(url)) return null;

  const title =
    meta("og:title") || document.title.replace("_哔哩哔哩_bilibili", "").trim();

  // author 多路径兜底
  const author =
    document.querySelector("meta[itemprop='name']")?.getAttribute("content") ||
    document.querySelector("a.up-name")?.textContent?.trim() ||
    (function () {
      try {
        const state = (window as unknown as { __INITIAL_STATE__?: BilibiliInitialState })
          .__INITIAL_STATE__;
        if (state?.upData?.name) return state.upData.name;
      } catch {
        /* ignore */
      }
      return "";
    })() ||
    "";

  const thumbnail = meta("og:image") || "";

  // duration（秒）
  let duration: number | null = null;
  try {
    const state = (window as unknown as { __INITIAL_STATE__?: BilibiliInitialState })
      .__INITIAL_STATE__;
    if (state?.videoData?.duration) {
      duration = parseInt(String(state.videoData.duration)) || null;
    }
  } catch {
    /* ignore */
  }

  return { url, title, author, thumbnail, duration, platform: "bilibili" };
}
