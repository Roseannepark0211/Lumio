/**
 * 快手元数据提取
 * - 仅在 /short-video/ /new-reco /profile 页提取
 * - 主要用 og 标签兜底
 */
import { commonOg } from "../shared/og";
import type { ExtractResult } from "../shared/types";

export function extractKuaishou(): ExtractResult | null {
  const url = window.location.href;
  if (!/\/(short-video|new-reco|profile)/.test(url)) return null;

  const info = commonOg();
  return {
    url,
    title: info.title,
    author: info.author,
    thumbnail: info.thumbnail,
    duration: info.duration,
    platform: "kuaishou",
  };
}
