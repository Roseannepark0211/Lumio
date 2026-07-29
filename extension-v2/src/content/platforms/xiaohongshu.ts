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
 *
 * ★ CSP 修复：原版用 inline script 注入（script.textContent = "..."）被小红书
 * CSP 的 script-src 指令拦截（不允许 'unsafe-inline'）。
 * 改用 chrome.scripting.executeScript({ world: "MAIN" }) 通过 background 中转，
 * 这是 MV3 标准做法，绕过 CSP 限制（scripting 权限已在 manifest 声明）。
 *
 * ★ 卡死修复：原超时 3000ms，小红书 __INITIAL_STATE__ 可能很大（含整个笔记列表），
 * executeScript({ world: "MAIN" }) 在主线程执行时会阻塞页面渲染。
 * 降到 1500ms，并在 background 端裁剪返回数据（只返回 noteDetailMap 首个 entry）。
 */
function readInitialState(timeout = 1500): Promise<XhsState | null> {
  return new Promise((resolve) => {
    let resolved = false;
    const done = (val: XhsState | null) => {
      if (resolved) return;
      resolved = true;
      resolve(val);
    };

    // 通过 background 调用 chrome.scripting.executeScript({ world: "MAIN" })
    try {
      chrome.runtime.sendMessage({ type: "xhs-read-state" }, (state) => {
        if (chrome.runtime.lastError) {
          console.log('[Lumio-XHS] xhs-read-state 错误:', chrome.runtime.lastError.message);
          done(null);
          return;
        }
        done((state as XhsState | null) || null);
      });
    } catch (e) {
      console.log('[Lumio-XHS] xhs-read-state 异常:', e);
      done(null);
    }

    // 超时兜底（executeScript 异常未回调时）
    setTimeout(() => done(null), timeout);
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
  const state = await readInitialState();

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
  // ★ 严格限定在 .media-container .swiper-slide 内，避免抓到评论区/推荐区/头像
  //
  // 小红书详情页当前帖子媒体 DOM 结构（从诊断数据逆向）：
  //   .media-container
  //     .xhs-slider-container
  //       .swiper
  //         .swiper-wrapper
  //           .swiper-slide[data-swiper-slide-index="0"]  ← 真实 slide
  //             .img-container
  //               .note-slider-img
  //                 <img src="...notes_pre_post/...!nd_dft_wlteh_webp_3">
  //           .swiper-slide[data-swiper-slide-index="1"]  ← 真实 slide
  //           .swiper-slide.swiper-slide-duplicate        ← 复制 slide（要排除）
  //
  // 评论区图片特征：parentClassName 含 "image-item" / "comment-image"
  // 推荐区图片特征：parentClassName 含 "cover mask ld"
  // 头像特征：src 含 "avatar" / class 含 "author-avatar"
  if (media_items.length === 0) {
    await waitForDomMedia(5000, 200);

    // 优先级 1：从 .media-container .swiper-slide 内提取（最精准）
    const swiperSlides = document.querySelectorAll(
      ".media-container .swiper-slide:not(.swiper-slide-duplicate)",
    );
    console.log("[Lumio-XHS] 找到 swiper-slide 数:", swiperSlides.length);

    for (const slide of Array.from(swiperSlides)) {
      // slide 内的 img（图片帖子）
      const imgs = slide.querySelectorAll("img[src]");
      for (const img of Array.from(imgs)) {
        const src = img.getAttribute("src");
        if (!src || !src.startsWith("http")) continue;
        if (src.includes("avatar") || src.includes("ns-avatar")) continue;
        const httpsSrc = toHttps(src);
        if (seenUrls.has(httpsSrc)) continue;
        seenUrls.add(httpsSrc);
        media_items.push({ url: httpsSrc, is_video: false });
        if (!thumbnail) thumbnail = httpsSrc;
      }

      // slide 内的 video（视频帖子）
      const vids = slide.querySelectorAll("video");
      for (const v of Array.from(vids)) {
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
        // video poster
        if (v.poster && v.poster.startsWith("http")) {
          const httpsP = toHttps(v.poster);
          if (!thumbnail && !seenUrls.has(httpsP)) {
            thumbnail = httpsP;
          }
        }
      }
    }

    // 优先级 2：.media-container 内的 video（视频帖子不一定有 swiper-slide）
    if (media_items.length === 0) {
      const mediaContainer = document.querySelector(".media-container");
      if (mediaContainer) {
        const vids = mediaContainer.querySelectorAll("video");
        for (const v of Array.from(vids)) {
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
          if (v.poster && v.poster.startsWith("http")) {
            const httpsP = toHttps(v.poster);
            if (!thumbnail && !seenUrls.has(httpsP)) {
              thumbnail = httpsP;
            }
          }
        }
      }
    }

    // 优先级 3：og:image 兜底（单图帖子）
    const ogImg = commonOg().thumbnail;
    if (media_items.length === 0 && ogImg) {
      const httpsO = toHttps(ogImg);
      media_items.push({ url: httpsO, is_video: false });
      if (!thumbnail) thumbnail = httpsO;
      seenUrls.add(httpsO);
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
