/**
 * HomePage 子组件：顶部预览区（图片/视频自适应宽高比）。
 *
 * 与 QML 版 HomePage.qml line 596-794 对齐：
 * - 横屏（aspectRatio > 1.2）：宽度优先，目标 480px 高
 * - 正方形/竖屏（aspectRatio <= 1.2）：高度优先，最大 580px
 * - 选中视频项显示 play 图标 + 视频占位
 * - 右下角 duration 徽章
 */

import { type VideoInfo, type MediaItem, thumbProxyUrl } from "../../api";
import type { SortedMediaItem } from "./MediaItemsList";

interface Props {
  previewInfo: VideoInfo;
  selectedItemIndex: number;
  sortedItems: SortedMediaItem[];
}

export function PreviewArea({ previewInfo, selectedItemIndex, sortedItems }: Props) {
  const selectedItem: MediaItem | null = selectedItemIndex >= 0
    ? (sortedItems.find((s) => s.orig_idx === selectedItemIndex)?.item ?? null)
    : null;

  const isVideo = selectedItem ? selectedItem.is_video : (previewInfo.items.length === 1 && previewInfo.items[0].is_video);
  const aspectRatio = computeAspectRatio(previewInfo, selectedItem, sortedItems);
  const height = aspectRatio > 1.2 ? 380 : 580;
  const previewSource = computePreviewSource(previewInfo, selectedItem);

  return (
    <div className="glass-card mb-4 p-4 animate-slide-up">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          预览
        </h3>
        <PlatformPill platform={previewInfo.platform} />
      </div>

      <div
        className="relative mx-auto flex items-center justify-center overflow-hidden rounded-xl bg-black/40"
        style={{ height, maxWidth: '100%' }}
      >
        {previewSource ? (
          <img
            src={previewSource}
            alt={previewInfo.title}
            className="max-h-full max-w-full object-contain"
            style={{ aspectRatio: String(aspectRatio) }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-text-muted">
            <VideoIcon className="h-12 w-12 opacity-50" />
          </div>
        )}

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
        <div className="text-sm font-medium text-text line-clamp-2">{previewInfo.title || '(无标题)'}</div>
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
  const labels: Record<string, string> = {
    youtube: "YouTube",
    instagram: "IG",
    x: "X",
    bilibili: "B站",
    douyin: "抖音",
    kuaishou: "快手",
    weibo: "微博",
    xiaohongshu: "小红书",
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
