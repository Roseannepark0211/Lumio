/**
 * Instagram 媒体提取（content script 模块）
 *
 * ★ 改为常驻 content script（不再用 executeScript 一次性注入）
 * 原因：executeScript + files 不等待 async Promise，导致返回 undefined
 *
 * ★ 实测发现（2026-07）：
 *   1. IG 头像 URL 路径含 t51.82787-19（非 t51.2885-19）
 *   2. 帖子媒体 URL 路径含 t51.82787-15
 *   3. /embed/ 端点可匿名访问，但只返回部分图（多图帖子）
 *   4. DOM 提取需要等待 SPA 渲染（5-10s）
 *   5. DOM 优先（已登录时完整），embed 兜底（未登录时）
 *
 * ★ 阶段 2 防御性增强（2026-07）：
 *   - waitForMedia 8s → 12s（IG SPA 渲染慢，尤其未登录时）
 *   - 扩大 CDN 白名单：fbcdn / cdninstagram / scontent-XXX
 *   - 多选择器兜底：article img / main img / [data-testid] 容器
 *   - /embed/ 失败时尝试 /embed/captioned/
 *   - srcset 解析支持 webp 格式
 */
import type { MediaItem } from "../../types";
import type { ExtractResult } from "../shared/types";

/** 判断是否为头像 URL */
function isAvatarUrl(url: string, alt?: string): boolean {
  if (url.includes("t51.82787-19") || url.includes("t51.2885-19")) return true;
  // 新版头像路径可能含 /profile_pic 或 _headshot
  if (url.includes("/profile_pic") || url.includes("_headshot")) return true;
  if (alt && (alt.includes("头像") || alt.toLowerCase().includes("avatar") || alt.toLowerCase().includes("profile"))) return true;
  return false;
}

/** 判断是否为小尺寸缩略图 */
function isSmallThumbnail(url: string): boolean {
  return (
    url.includes("s100x100") ||
    url.includes("s150x150") ||
    url.includes("s320x320") ||
    // 新版可能用 /150x150/ 路径段
    url.includes("/150x150/") ||
    url.includes("/100x100/")
  );
}

/**
 * 判断是否为 IG CDN URL
 * ★ 扩大白名单：fbcdn / cdninstagram / scontent-XXX.cdninstagram
 */
function isIgCdnUrl(url: string): boolean {
  return (
    url.includes("fbcdn") ||
    url.includes("cdninstagram") ||
    // scontent-XXX.cdninstagram.com
    /^https:\/\/scontent[^.]*\.(cdninstagram|fbcdn)\./.test(url) ||
    // 新版可能用 install-in-iad CDN
    url.includes("install-in-iad")
  );
}

/** 等待 DOM 媒体元素出现 */
function waitForMedia(maxWait = 12000, interval = 200): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now();
    function check() {
      const hasVideo = document.querySelectorAll("video").length > 0;
      const hasImg =
        document.querySelectorAll(
          "img[src*='cdninstagram'], img[src*='fbcdn'], img[src*='scontent']",
        ).length > 0;
      // 兜底：article 标签存在也算（说明 SPA 已渲染）
      const hasArticle = document.querySelectorAll("article").length > 0;
      if (hasVideo || hasImg || hasArticle || Date.now() - start >= maxWait) {
        resolve();
        return;
      }
      setTimeout(check, interval);
    }
    check();
  });
}

/**
 * 等待指定毫秒
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 查找 IG carousel 的"下一张"按钮
 *
 * ★ IG carousel "下一张"按钮特征（桌面版）：
 *   - 覆盖在图片右侧的半透明圆形按钮（绝对/固定定位）
 *   - 垂直居中在图片区域
 *   - 内含 svg 箭头图标
 *   - aria-label 含 "Next" / "Go next" / "下一项"（有则最可靠）
 *
 * ★ 必须排除的按钮（footer 操作栏）：
 *   - 分享/转发（paper plane 图标）
 *   - 收藏（bookmark 图标）
 *   - 点赞/评论（heart/speech bubble 图标）
 *   - 更多选项（三点图标）
 *   这些按钮也在右半部分且有 svg，但位于 footer 流式布局，不是覆盖按钮
 *
 * ★ 精准识别策略（按可靠性排序）：
 *   1. aria-label 匹配 next 模式（最可靠）
 *   2. 无 aria-label 时，必须是"覆盖在图片上的圆形按钮"：
 *      - position: absolute / fixed（覆盖定位）
 *      - width ≈ height（圆形）
 *      - 垂直位置在图片区域内（top < 图片 bottom）
 *   3. 排除 aria-label 含 share/save/more/comment/like 等
 */
function findNextButton(detailRoot: Element): HTMLButtonElement | null {
  // ★ next 按钮的 aria-label 匹配模式（多语言）
  const nextPatterns = [/next/i, /go\s*next/i, /下一/i, /后一/i, /继续/i];
  // ★ 必须排除的 aria-label（footer 操作按钮）
  const excludePatterns = [
    /share/i, /save/i, /bookmark/i, /more/i, /options/i, /comment/i, /like/i, /heart/i,
    /转发/i, /分享/i, /收藏/i, /评论/i, /点赞/i, /更多/i,
  ];

  const buttonSelectors = [
    "button[aria-label]",
    "button[role='button']",
    "button",
  ];

  for (const sel of buttonSelectors) {
    const buttons = detailRoot.querySelectorAll(sel);
    for (const btn of Array.from(buttons)) {
      const htmlBtn = btn as HTMLButtonElement;
      // 跳过 disabled
      if (htmlBtn.disabled) continue;
      // 跳过 cursor: not-allowed
      const cursor = window.getComputedStyle(htmlBtn).cursor;
      if (cursor === "not-allowed") continue;

      const ariaLabel = htmlBtn.getAttribute("aria-label") || "";

      // ★ 排除 footer 操作按钮（分享/收藏/评论/点赞/更多）
      if (ariaLabel && excludePatterns.some((p) => p.test(ariaLabel))) continue;

      // 优先级 1：aria-label 匹配 next
      if (ariaLabel && nextPatterns.some((p) => p.test(ariaLabel))) {
        return htmlBtn;
      }

      // 优先级 2：无 aria-label，必须是覆盖在图片上的圆形按钮
      if (!ariaLabel) {
        const hasSvg = htmlBtn.querySelector("svg");
        if (!hasSvg) continue;

        const style = window.getComputedStyle(htmlBtn);
        const rect = htmlBtn.getBoundingClientRect();
        const rootRect = detailRoot.getBoundingClientRect();

        // 2a. 必须在右半部分
        const isRightHalf = rect.left > rootRect.left + rootRect.width / 2;
        if (!isRightHalf) continue;

        // 2b. 必须是绝对/固定定位（覆盖在图片上，排除 footer 流式布局按钮）
        if (style.position !== "absolute" && style.position !== "fixed") continue;

        // 2c. 必须是圆形（width ≈ height，carousel 箭头按钮是圆形）
        const ratio = rect.width / rect.height;
        if (ratio < 0.7 || ratio > 1.4) continue;

        // 2d. 垂直位置必须在图片区域内（不在 footer）
        if (rect.top > rootRect.bottom - 10) continue;

        return htmlBtn;
      }
    }
  }

  return null;
}

/**
 * 检测当前页是否为 IG carousel（多图帖子）
 *
 * ★ 判断依据：
 *   1. detailRoot 内有"下一张"按钮
 *   2. 或 detailRoot 内有多个 [role='group'][aria-roledescription='slide']
 *   3. 或 detailRoot 内有 indicator dots（小圆点导航）
 */
function isCarousel(detailRoot: Element): boolean {
  // 1. 有"下一张"按钮
  if (findNextButton(detailRoot)) return true;

  // 2. 有 slide role
  const slides = detailRoot.querySelectorAll(
    "[role='group'][aria-roledescription='slide']",
  );
  if (slides.length > 1) return true;

  // 3. 有 indicator dots（通常是 div + 多个 button/span）
  // IG 的 dots 通常是 [role='tablist'] 或含多个 [role='button'] 的容器
  const tablist = detailRoot.querySelector("[role='tablist']");
  if (tablist) return true;

  return false;
}

/**
 * ★ 方案 A 核心：自动翻页提取完整 carousel
 *
 * 流程：
 *   1. 先 collectFromContainer 抓当前可见的图
 *   2. 循环点击"下一张"按钮，每次等待新 img 渲染
 *   3. 重新 collectFromContainer，去重合并新 URL
 *   4. 直到按钮 disabled / 消失 / 达到最大点击次数
 *
 * ★ 保护机制：
 *   - 最大点击 30 次（IG carousel 上限 20 张，留余量）
 *   - 每次点击后等 300ms + 等 img 出现（最多 2s）
 *   - 整体超时 30s（避免卡死）
 *   - URL 去重（seenUrls）
 *
 * ★ 副作用：会改变用户当前查看的 slide（翻到最后一张）
 *   可接受：用户右键发送后通常会离开页面
 */
async function extractAllCarouselImages(
  detailRoot: Element,
  collectFn: (container: Element) => void,
  seenUrls: Set<string>,
  mediaCountBefore: number,
): Promise<void> {
  const MAX_CLICKS = 30;
  const MAX_TOTAL_WAIT = 30000; // 30s 整体超时
  const startTime = Date.now();

  let clickCount = 0;
  let noProgressCount = 0; // 连续无新图次数

  while (clickCount < MAX_CLICKS && Date.now() - startTime < MAX_TOTAL_WAIT) {
    const nextBtn = findNextButton(detailRoot);
    if (!nextBtn) {
      console.log(`[Lumio-IG] carousel: 无下一张按钮，停止（点击 ${clickCount} 次）`);
      break;
    }

    // 记录点击前的 URL 数量
    const beforeCount = seenUrls.size;

    // 点击
    nextBtn.click();
    clickCount++;

    // 等待新 img 渲染（300ms 基础 + 最多 2s 等 img 出现）
    await sleep(300);
    const imgWaitStart = Date.now();
    while (Date.now() - imgWaitStart < 2000) {
      // 检查是否有新 img 加载（src 不在 seenUrls 中）
      const newImgs = detailRoot.querySelectorAll(
        "img[src*='cdninstagram'], img[src*='fbcdn'], img[src*='scontent']",
      );
      let hasNew = false;
      for (const img of Array.from(newImgs)) {
        const src = img.getAttribute("src") || "";
        if (src && !seenUrls.has(src)) {
          hasNew = true;
          break;
        }
      }
      if (hasNew) break;
      await sleep(150);
    }

    // 重新采集
    collectFn(detailRoot);

    const afterCount = seenUrls.size;
    const newAdded = afterCount - beforeCount;
    console.log(
      `[Lumio-IG] carousel: 第 ${clickCount} 次点击后新增 ${newAdded} 张（总计 ${afterCount}）`,
    );

    // 连续 3 次无新图，认为已到末尾
    if (newAdded === 0) {
      noProgressCount++;
      if (noProgressCount >= 3) {
        console.log(`[Lumio-IG] carousel: 连续 3 次无新图，停止`);
        break;
      }
    } else {
      noProgressCount = 0;
    }
  }

  console.log(
    `[Lumio-IG] carousel 翻页完成：共点击 ${clickCount} 次，从 ${mediaCountBefore} 张增长到 ${seenUrls.size} 张`,
  );
}

/**
 * 从 srcset 解析最高分辨率 URL
 *
 * srcset 格式有两种：
 * - "url1 1x, url2 2x"（密度描述符）
 * - "url1 640w, url2 1080w"（宽度描述符）
 *
 * ★ 修复：原来取 entries[length-1]，但实际 srcset 顺序可能是
 *   "1080w, 720w, 640w, 480w, 320w, 240w"（高到低），
 *   取最后一个 = 最低分辨率，错误。
 *
 * 正确做法：解析宽度数字，取最大值；密度描述符取最大 x。
 */
function pickHighestResFromSrcset(srcset: string): string | null {
  const entries = srcset.split(",").map((s) => s.trim()).filter(Boolean);
  if (entries.length === 0) return null;
  if (entries.length === 1) {
    return entries[0].split(/\s+/)[0] || null;
  }

  let bestUrl: string | null = null;
  let bestScore = -1;

  for (const entry of entries) {
    const parts = entry.split(/\s+/);
    const url = parts[0];
    const descriptor = parts[1] || "";

    if (!url || !url.startsWith("http")) continue;

    let score = 0;
    // 宽度描述符："1080w"
    const widthMatch = descriptor.match(/^(\d+)w$/);
    if (widthMatch) {
      score = parseInt(widthMatch[1], 10);
    }
    // 密度描述符："2x"
    const densityMatch = descriptor.match(/^(\d+(?:\.\d+)?)x$/);
    if (densityMatch) {
      score = parseFloat(densityMatch[1]) * 1000; // 放大方便统一比较
    }
    // 无描述符，给默认分
    if (!descriptor) score = 500;

    if (score > bestScore) {
      bestScore = score;
      bestUrl = url;
    }
  }

  return bestUrl;
}

export async function extractInstagram(): Promise<ExtractResult | null> {
  const url = window.location.href;
  // 仅在 /p/ 或 /reel/ 页提取
  if (!/\/(p|reel)\//.test(url)) return null;

  const parts = location.pathname.split("/").filter(Boolean);
  let author = "";
  if (parts.length >= 2 && (parts[1] === "p" || parts[1] === "reel")) {
    author = parts[0];
  }

  const title =
    document.querySelector("meta[property='og:title']")?.getAttribute("content") ||
    document.querySelector("meta[name='description']")?.getAttribute("content") ||
    "Instagram post";

  const ogImage =
    document.querySelector("meta[property='og:image']")?.getAttribute("content") || "";

  const media_items: MediaItem[] = [];
  const seenUrls = new Set<string>();

  function addMedia(rawUrl: string, isVideo: boolean, alt?: string): boolean {
    if (!rawUrl || !rawUrl.startsWith("http")) return false;
    if (rawUrl.startsWith("blob:")) return false;
    if (!isIgCdnUrl(rawUrl)) return false;
    if (isAvatarUrl(rawUrl, alt)) return false;
    if (!isVideo && isSmallThumbnail(rawUrl)) return false;
    if (seenUrls.has(rawUrl)) return false;
    seenUrls.add(rawUrl);
    media_items.push({ url: rawUrl, is_video: isVideo });
    return true;
  }

  // ── 优先级 1：DOM 提取 ──────────────────────────────────────────
  await waitForMedia(12000, 200);

  // ★ 精准定位详情容器（避免抓到推荐区/相关帖子）
  // IG 详情页两种渲染模式：
  //   1. 从主页点击进入：div[role='dialog'] 模态框包裹当前帖子 article
  //   2. 直接访问 /p/{id}/：main 内第一个 article 是当前帖子
  // 推荐区/相关帖子也是 article，必须选对容器
  const detailRoot = locateDetailRoot();

  // 视频
  const ogVideo = document.querySelector("meta[property='og:video']");
  const ogVideoContent = ogVideo?.getAttribute("content");
  if (ogVideoContent) addMedia(ogVideoContent, true);

  /**
   * 从容器内提取所有媒体（video + img + srcset）
   * ★ 含多图帖子的所有 slide（包括隐藏的，通过 srcset 和 data-src 兜底）
   */
  const collectFromContainer = (container: Element) => {
    // 视频
    const vids = container.querySelectorAll("video");
    for (const v of Array.from(vids)) {
      const candidates = [v.src, v.querySelector("source")?.src || "", v.currentSrc];
      for (const u of candidates) addMedia(u, true);
    }

    // 图片
    const imgSelectors = [
      "img[src*='cdninstagram']",
      "img[src*='fbcdn']",
      "img[src*='scontent']",
    ];
    const cdnImgs = container.querySelectorAll(imgSelectors.join(", "));
    for (const img of Array.from(cdnImgs)) {
      const src = img.getAttribute("src");
      const alt = img.getAttribute("alt") || "";
      if (src) addMedia(src, false, alt);
    }

    // srcset 图片（取最高分辨率）
    const srcsetImgs = container.querySelectorAll(
      "img[srcset*='cdninstagram'], img[srcset*='fbcdn'], img[srcset*='scontent']",
    );
    for (const img of Array.from(srcsetImgs)) {
      const srcset = img.getAttribute("srcset") || "";
      const alt = img.getAttribute("alt") || "";
      if (srcset) {
        const bestUrl = pickHighestResFromSrcset(srcset);
        if (bestUrl) addMedia(bestUrl, false, alt);
      }
    }
  };

  if (detailRoot) {
    collectFromContainer(detailRoot);

    // ★ 方案 A：检测到 carousel 时自动翻页提取完整图片
    // 解决"IG carousel DOM 只渲染当前 slide + 相邻 slide（通常 4 张）"的限制
    // 通过模拟点击"下一张"按钮逐张翻页，去重合并所有 slide 的图片 URL
    const initialCount = media_items.length;
    if (isCarousel(detailRoot)) {
      console.log(
        `[Lumio-IG] 检测到 carousel，开始自动翻页（初始 ${initialCount} 张）`,
      );
      await extractAllCarouselImages(
        detailRoot,
        collectFromContainer,
        seenUrls,
        initialCount,
      );
    }
  }

  // ★ 全局兜底：详情容器没找到或没抓到时，用全局 article（第一个）
  if (media_items.length === 0) {
    const firstArticle = document.querySelector("article");
    if (firstArticle) collectFromContainer(firstArticle);
  }

  // ★ 最后兜底：og:image
  if (media_items.length === 0 && ogImage && !isAvatarUrl(ogImage)) {
    addMedia(ogImage, false);
  }

  // ── 优先级 2：/embed/ 兜底（DOM 没找到时）──────────────────────
  if (media_items.length === 0) {
    let shortcode = "";
    for (let i = 0; i < parts.length - 1; i++) {
      if (parts[i] === "p" || parts[i] === "reel") {
        shortcode = parts[i + 1];
        break;
      }
    }
    if (shortcode) {
      const isReel = parts[0] === "reel" || parts[1] === "reel";
      // ★ 尝试多个 embed 路径（IG 限制变严，需要兜底）
      const embedPaths = isReel
        ? [`/reel/${shortcode}/embed/`, `/reel/${shortcode}/embed/captioned/`]
        : [`/p/${shortcode}/embed/`, `/p/${shortcode}/embed/captioned/`];

      for (const embedPath of embedPaths) {
        if (media_items.length > 0) break;
        try {
          const resp = await fetch(embedPath, { credentials: "omit" });
          if (!resp.ok) continue;
          const html = await resp.text();
          const doc = new DOMParser().parseFromString(html, "text/html");

          const embedVideos = doc.querySelectorAll("video");
          for (const v of Array.from(embedVideos)) {
            const candidates = [v.src, v.querySelector("source")?.src || "", v.currentSrc];
            for (const u of candidates) addMedia(u, true);
          }

          // embed 页内 img（含 src 和 srcset）
          const embedImgs = doc.querySelectorAll(
            "img[src*='fbcdn'], img[src*='cdninstagram'], img[src*='scontent']",
          );
          for (const img of Array.from(embedImgs)) {
            const imgUrl = img.getAttribute("src");
            const imgAlt = img.getAttribute("alt") || "";
            if (imgUrl) addMedia(imgUrl, false, imgAlt);

            // 也尝试 srcset（取最高分辨率）
            const srcset = img.getAttribute("srcset") || "";
            if (srcset) {
              const bestUrl = pickHighestResFromSrcset(srcset);
              if (bestUrl) addMedia(bestUrl, false, imgAlt);
            }
          }
        } catch (e) {
          console.log(`IG embed ${embedPath} failed:`, e);
        }
      }
    }
  }

  // 兜底：og:image（embed 也失败时）
  if (media_items.length === 0 && ogImage && !isAvatarUrl(ogImage)) {
    addMedia(ogImage, false);
  }

  const thumbnail = media_items.find((m) => !m.is_video)?.url || ogImage;

  return {
    url,
    title,
    author,
    thumbnail,
    platform: "instagram",
    media_items,
    duration: null,
    direct_url: media_items.length > 0 ? media_items[0].url : "",
  };
}

/**
 * 定位 IG 详情页主容器
 *
 * IG 详情页两种渲染模式：
 *   1. 从主页/.profile 点击帖子 → 弹出 div[role='dialog'] 模态框
 *      模态框内的 article 是当前帖子（推荐区 article 在模态框外）
 *   2. 直接访问 /p/{id}/ 或 /reel/{id}/ → main 内渲染详情
 *      main 内第一个 article 通常是当前帖子
 *
 * ★ 必须精准定位，否则会抓到推荐区/相关帖子
 */
function locateDetailRoot(): Element | null {
  // 优先级 1：模态框（从主页点击进入）
  const dialog = document.querySelector("div[role='dialog']");
  if (dialog) {
    const article = dialog.querySelector("article");
    if (article) return article;
    return dialog;
  }

  // 优先级 2：main 内第一个 article（直接访问详情页 URL）
  const main = document.querySelector("main");
  if (main) {
    const article = main.querySelector("article");
    if (article) return article;
    return main;
  }

  // 优先级 3：全局第一个 article（最后兜底）
  return document.querySelector("article");
}
