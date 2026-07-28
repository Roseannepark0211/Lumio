/**
 * 小红书元数据提取
 * - 仅在 /explore/{id} 或 /discovery/item/{id} 页提取
 *
 * ★ 关键问题：content script 运行在隔离 JS 上下文，无法访问 window.__INITIAL_STATE__
 * ★ 解决方案：注入 <script> 标签到主世界，读取 __INITIAL_STATE__ 后通过 postMessage 回传
 *
 * - author 从 __INITIAL_STATE__.note.user.nickname 提取
 * - 所有 URL 升级为 HTTPS（原数据是 HTTP，会被 mixed content 拦截）
 */
import { commonOg } from "../shared/og";
import type { ExtractResult } from "../shared/types";
import type { MediaItem } from "../../types";

/** 小红书 __INITIAL_STATE__ 简化类型 */
interface XhsImageInfo {
  imageScene?: string;
  url?: string;
}
interface XhsImage {
  fileId?: string;
  height?: number;
  width?: number;
  infoList?: XhsImageInfo[];
  urlDefault?: string;
  livePhoto?: boolean;
  url?: string;
  traceId?: string;
  urlPre?: string;
  stream?: unknown;
}
interface XhsNote {
  title?: string;
  desc?: string;
  type?: string;
  user?: { nickname?: string; nickName?: string };
  imageList?: XhsImage[];
  video?: {
    media?: {
      stream?: {
        h264?: Array<{ masterUrl?: string; backupUrls?: string[] }>;
        h265?: Array<{ masterUrl?: string; backupUrls?: string[] }>;
      };
    };
  };
}
interface XhsState {
  note?: {
    noteDetailMap?: Record<string, { note?: XhsNote }>;
  };
}

/** 将 HTTP URL 升级为 HTTPS */
function toHttps(url: string): string {
  if (!url) return url;
  if (url.startsWith("http://")) {
    return "https://" + url.slice(7);
  }
  return url;
}

/**
 * 从主世界读取 __INITIAL_STATE__
 * 注入 <script> 标签，读取后通过 postMessage 回传
 */
function readInitialState(timeout = 3000): Promise<XhsState | null> {
  return new Promise((resolve) => {
    const requestId = `xhs-state-${Date.now()}-${Math.random()}`;

    function handler(event: MessageEvent) {
      if (event.source !== window) return;
      const data = event.data;
      if (data && data.type === "lumio-xhs-state" && data.requestId === requestId) {
        window.removeEventListener("message", handler);
        resolve(data.state || null);
      }
    }
    window.addEventListener("message", handler);

    // 注入 <script> 到主世界
    const script = document.createElement("script");
    script.textContent = `
      (function() {
        var requestId = ${JSON.stringify(requestId)};
        var state = window.__INITIAL_STATE__ || null;
        window.postMessage({ type: 'lumio-xhs-state', requestId: requestId, state: state }, '*');
      })();
    `;
    (document.head || document.documentElement).appendChild(script);
    script.remove();

    // 超时
    setTimeout(() => {
      window.removeEventListener("message", handler);
      resolve(null);
    }, timeout);
  });
}

/** 等待 DOM 媒体元素出现 */
function waitForDomMedia(maxWait = 5000, interval = 200): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now();
    function check() {
      const hasVideo = document.querySelectorAll("video").length > 0;
      const hasImg = document.querySelectorAll(
        "img[src*='xhscdn'], img[src*='sns-img']",
      ).length > 0;
      if (hasVideo || hasImg || Date.now() - start >= maxWait) {
        resolve();
        return;
      }
      setTimeout(check, interval);
    }
    check();
  });
}

export async function extractXiaohongshu(): Promise<ExtractResult | null> {
  const url = window.location.href;
  if (!/\/(explore|discovery\/item)\//.test(url)) return null;

  const idMatch = url.match(/\/(?:explore|discovery\/item)\/([a-zA-Z0-9]+)/);
  const noteId = idMatch?.[1] || "";

  let title = commonOg().title || document.title.replace(" - 小红书", "").trim();
  let author = "";
  let thumbnail = commonOg().thumbnail;
  const media_items: MediaItem[] = [];
  const seenUrls = new Set<string>();

  // ── 优先级 1：从 __INITIAL_STATE__ 提取（通过 postMessage）────────
  const state = await readInitialState(3000);

  if (state?.note?.noteDetailMap) {
    const detail =
      (noteId && state.note.noteDetailMap[noteId]) ||
      Object.values(state.note.noteDetailMap)[0];

    const note = detail?.note;
    if (note) {
      if (note.title) title = note.title;
      if (note.user?.nickname) author = note.user.nickname;
      else if (note.user?.nickName) author = note.user.nickName;

      // 图片列表
      const imageList = note.imageList;
      if (imageList && imageList.length > 0) {
        for (const img of imageList) {
          let imgUrl = img.urlDefault || "";
          if (!imgUrl && img.infoList) {
            const dft = img.infoList.find((i) => i.imageScene === "WB_DFT");
            if (dft?.url) imgUrl = dft.url;
          }
          if (!imgUrl) imgUrl = img.url || img.urlPre || "";
          imgUrl = toHttps(imgUrl);
          if (imgUrl && !seenUrls.has(imgUrl)) {
            seenUrls.add(imgUrl);
            media_items.push({ url: imgUrl, is_video: false });
            if (!thumbnail) thumbnail = imgUrl;
          }
        }
      }

      // 视频
      if (note.video?.media?.stream) {
        const { h264, h265 } = note.video.media.stream;
        const streams = h264 || h265 || [];
        if (streams.length > 0) {
          const masterUrl = toHttps(streams[0].masterUrl || "");
          if (masterUrl && !seenUrls.has(masterUrl)) {
            seenUrls.add(masterUrl);
            media_items.push({ url: masterUrl, is_video: true });
          }
        }
      }
    }
  }

  // ── 优先级 2：DOM 提取（__INITIAL_STATE__ 不可用时）────────
  if (media_items.length === 0) {
    await waitForDomMedia(5000, 200);

    const domImgs = document.querySelectorAll(
      "img[src*='xhscdn'], img[src*='sns-img']",
    );
    for (const img of Array.from(domImgs)) {
      const src = img.getAttribute("src");
      if (!src || !src.startsWith("http")) continue;
      if (src.includes("avatar") || src.includes("ns-avatar")) continue;
      if (src.includes("/avatar/") || src.includes("cut=")) continue;
      const httpsSrc = toHttps(src);
      if (seenUrls.has(httpsSrc)) continue;
      seenUrls.add(httpsSrc);
      media_items.push({ url: httpsSrc, is_video: false });
      if (!thumbnail) thumbnail = httpsSrc;
    }

    const domVideos = document.querySelectorAll("video");
    for (const v of Array.from(domVideos)) {
      const candidates = [v.src, v.currentSrc].filter(
        (u): u is string => !!u && u.startsWith("http") && !u.startsWith("blob:"),
      );
      for (const u of candidates) {
        const httpsU = toHttps(u);
        if (!seenUrls.has(httpsU)) {
          seenUrls.add(httpsU);
          media_items.push({ url: httpsU, is_video: true });
        }
      }
    }
  }

  if (!thumbnail) thumbnail = commonOg().thumbnail;
  if (media_items.length === 0 && thumbnail) {
    media_items.push({ url: thumbnail, is_video: false });
  }

  return {
    url,
    title,
    author,
    thumbnail,
    platform: "xiaohongshu",
    media_items,
    duration: null,
    direct_url: media_items.length > 0 ? media_items[0].url : "",
  };
}
