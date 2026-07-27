/**
 * HomePage 子组件：顶部预览区（图片/视频自适应宽高比）。
 *
 * 与 QML 版 HomePage.qml line 596-794 对齐：
 * - 横屏（aspectRatio > 1.2）：宽度优先，目标 480px 高
 * - 正方形/竖屏（aspectRatio <= 1.2）：高度优先，最大 580px
 * - 选中视频项显示 play 图标 + 视频占位
 * - 右下角 duration 徽章
 */

import { useEffect, useState } from "react";
import { type VideoInfo, type MediaItem, thumbProxyUrl } from "../../api";
import type { SortedMediaItem } from "./MediaItemsList";
import { useI18n } from "../../i18n";

interface Props {
  previewInfo: VideoInfo;
  selectedItemIndex: number;
  sortedItems: SortedMediaItem[];
}

export function PreviewArea({ previewInfo, selectedItemIndex, sortedItems }: Props) {
  const { tr } = useI18n();
  const selectedItem: MediaItem | null = selectedItemIndex >= 0
    ? (sortedItems.find((s) => s.orig_idx === selectedItemIndex)?.item ?? null)
    : null;

  const isVideo = selectedItem ? selectedItem.is_video : (previewInfo.items.length === 1 && previewInfo.items[0].is_video);
  const aspectRatio = computeAspectRatio(previewInfo, selectedItem, sortedItems);
  const height = aspectRatio > 1.2 ? 380 : 580;
  const previewSource = computePreviewSource(previewInfo, selectedItem);

  // —— 从素材提取主色注入灯带 ——
  // 容器尺寸随素材变化，旋转动画会显得突兀；改用静态灯带 + 主色呼吸 + 粒子绕行
  // 主色提取：用 fetch 拿 blob 转 ObjectURL，避免 crossOrigin canvas 污染
  const [flowColor, setFlowColor] = useState<string>("rgba(122, 92, 230, 0.8)");

  useEffect(() => {
    if (!previewSource) {
      setFlowColor("rgba(122, 92, 230, 0.8)");
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;

    fetch(previewSource)
      .then((r) => r.blob())
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
          if (cancelled) return;
          const color = extractDominantColor(img);
          if (color) setFlowColor(color);
          if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
        img.onerror = () => {
          if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
        img.src = objectUrl;
      })
      .catch(() => { /* 保持默认色 */ });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [previewSource]);

  return (
    <div className="glass-card mb-4 p-4 animate-slide-up">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          {tr("preview")}
        </h3>
        <PlatformPill platform={previewInfo.platform} />
      </div>

      {/* 容器尺寸计算：用 maxWidth（= maxHeight * aspectRatio）反向限制宽度，
          aspect-ratio 自动推导 height，确保容器永远紧贴素材，无空白深灰区域。
          - maxHeight=380 时 maxWidth=380*aspect（横屏典型 ~675px）
          - maxHeight=580 时 maxWidth=580*aspect（竖屏 9:16 ~326px）
          - 父容器更窄时 maxWidth:100% 兜底，aspect-ratio 反算出更小 height */}
      <div
        className="relative mx-auto overflow-hidden rounded-xl"
        style={{
          aspectRatio: String(aspectRatio),
          maxWidth: `min(100%, ${height}px * ${aspectRatio})`,
          // 注入主色给 .flow-border 的 CSS 变量
          ["--flow-color" as string]: flowColor,
        }}
      >
        {previewSource ? (
          <>
            {/* 背景层：素材模糊放大版填充容器，Apple Music 风。
                主体居中清晰显示，背景填充消除黑边并提供色彩延伸 */}
            <img
              src={previewSource}
              alt=""
              aria-hidden
              className="absolute inset-0 h-full w-full scale-110 object-cover blur-md opacity-45"
            />
            {/* 前景层：清晰主体 */}
            <img
              src={previewSource}
              alt={previewInfo.title}
              className="relative h-full w-full object-contain"
            />
          </>
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-black/40 text-text-muted">
            <VideoIcon className="h-12 w-12 opacity-50" />
          </div>
        )}

        {/* 灯带边框：颜色随素材主色变化，呼吸动画 */}
        <span className="flow-border" aria-hidden />

        {/* 粒子绕边框跑：4 个粒子均匀分布，8s 一圈 */}
        <span
          className="flow-particle"
          aria-hidden
          style={{ animationDelay: "0s" }}
        />
        <span
          className="flow-particle"
          aria-hidden
          style={{ animationDelay: "-2s" }}
        />
        <span
          className="flow-particle"
          aria-hidden
          style={{ animationDelay: "-4s" }}
        />
        <span
          className="flow-particle"
          aria-hidden
          style={{ animationDelay: "-6s" }}
        />

        {/* 视频占位 play 图标 */}
        {isVideo && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-black/50 backdrop-blur-sm">
              <PlayIcon className="h-8 w-8 text-white" />
            </div>
          </div>
        )}

        {/* 右下角 duration 徽章 */}
        {previewInfo.duration > 0 && (
          <div className="absolute bottom-2 right-2 rounded-md bg-black/70 px-2 py-0.5 font-mono text-xs text-white backdrop-blur-sm">
            {formatDuration(previewInfo.duration)}
          </div>
        )}
      </div>

      {/* 标题/作者/发布时间 */}
      <div className="mt-3 space-y-1">
        <div className="text-sm font-medium text-text line-clamp-2">{previewInfo.title || `(${tr("untitled")})`}</div>
        <div className="flex items-center gap-3 text-xs text-text-muted">
          {previewInfo.author && <span>@{previewInfo.author}</span>}
          {previewInfo.post_time && <span>{previewInfo.post_time}</span>}
        </div>
      </div>
    </div>
  );
}

/** 计算预览图源 URL */
function computePreviewSource(info: VideoInfo, selectedItem: MediaItem | null): string {
  if (selectedItem && !selectedItem.is_video && selectedItem.url) {
    return thumbProxyUrl(selectedItem.url);
  }
  if (info.thumbnail) {
    return thumbProxyUrl(info.thumbnail);
  }
  return "";
}

/** 从图片提取主色：缩到 32x32，遍历像素累加 RGB 取均值，
 *  然后提升饱和度让灯带颜色更鲜艳（避免纯灰/纯黑素材时灯带不可见）。
 *  返回 rgba(r,g,b,0.85) 格式供 CSS 变量直接用。
 *  返回 null 表示提取失败（图片全透明或尺寸为 1x1），调用方保持默认色。 */
function extractDominantColor(img: HTMLImageElement): string | null {
  // 后端 thumb-proxy 失败时返回 1x1 透明 GIF，直接跳过避免无效计算
  if (img.naturalWidth <= 1 || img.naturalHeight <= 1) return null;
  const SIZE = 32;
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  let data: Uint8ClampedArray;
  try {
    ctx.drawImage(img, 0, 0, SIZE, SIZE);
    data = ctx.getImageData(0, 0, SIZE, SIZE).data;
  } catch {
    // canvas 被 CORS 污染会抛 SecurityError
    return null;
  }
  let r = 0, g = 0, b = 0, count = 0;
  // 跳过完全透明像素，避免 PNG 透明区域影响均值
  for (let i = 0; i < data.length; i += 4) {
    const a = data[i + 3];
    if (a < 30) continue;
    r += data[i];
    g += data[i + 1];
    b += data[i + 2];
    count++;
  }
  if (count === 0) return null;
  r = Math.round(r / count);
  g = Math.round(g / count);
  b = Math.round(b / count);

  // 提升 saturation & lightness：转 HSL 拉伸后转回 RGB
  const hsl = rgbToHsl(r, g, b);
  hsl[1] = Math.min(1, hsl[1] * 1.8 + 0.35);   // 饱和度+80%，下限 0.35 确保鲜艳
  hsl[2] = Math.min(0.65, Math.max(0.5, hsl[2])); // 亮度限制在 0.5-0.65，避免太暗或太亮
  const [r2, g2, b2] = hslToRgb(hsl[0], hsl[1], hsl[2]);
  return `rgba(${r2}, ${g2}, ${b2}, 0.85)`;
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h /= 6;
  }
  return [h, s, l];
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  let r: number, g: number, b: number;
  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p: number, q: number, t: number) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1/6) return p + (q - p) * 6 * t;
      if (t < 1/2) return q;
      if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1/3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1/3);
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

/** 计算预览区宽高比 */
function computeAspectRatio(info: VideoInfo, selectedItem: MediaItem | null, sortedItems: SortedMediaItem[]): number {
  // 优先用选中项的 width/height
  if (selectedItem && selectedItem.width > 0 && selectedItem.height > 0) {
    return selectedItem.width / selectedItem.height;
  }
  // 多项帖但未选中：用第一项
  if (sortedItems.length > 0) {
    const first = sortedItems[0].item;
    if (first.width > 0 && first.height > 0) {
      return first.width / first.height;
    }
    // 视频项无尺寸时，抖音/快手默认 9:16，其他默认 16:9
    if (first.is_video) {
      return (info.platform === "douyin" || info.platform === "kuaishou") ? 9 / 16 : 16 / 9;
    }
    // 图片项无尺寸时，抖音/快手默认 1:1，其他默认 16:9
    return (info.platform === "douyin" || info.platform === "kuaishou") ? 1 : 16 / 9;
  }
  // 单项帖：用 info.items[0]
  if (info.items.length > 0) {
    const it = info.items[0];
    if (it.width > 0 && it.height > 0) return it.width / it.height;
  }
  return 16 / 9;
}

/** 格式化时长（QML 版只支持 MM:SS，超过 1 小时会错误，这里改为 HH:MM:SS） */
function formatDuration(sec: number): string {
  if (sec <= 0) return "0:00";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

function PlatformPill({ platform }: { platform: string }) {
  const { tr } = useI18n();
  const labels: Record<string, string> = {
    youtube: "YouTube",
    instagram: "IG",
    x: "X",
    bilibili: tr("platform_bilibili"),
    douyin: tr("platform_douyin"),
    kuaishou: tr("platform_kuaishou"),
    weibo: tr("platform_weibo"),
    xiaohongshu: tr("platform_xiaohongshu"),
  };
  return (
    <span className="pill-accent">{labels[platform] || platform}</span>
  );
}

function VideoIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="6" width="14" height="12" rx="2" />
      <path d="M22 8l-6 4 6 4V8z" />
    </svg>
  );
}

function PlayIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <polygon points="6 4 20 12 6 20 6 4" />
    </svg>
  );
}
