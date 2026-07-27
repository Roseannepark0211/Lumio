/**
 * HomePage 子组件：Media Items 横向列表（多图/多视频帖的子项切换）。
 *
 * 与 QML 版 HomePage.qml line 378-591 对齐：
 * - 视频项在前、图片在后，按 orig_idx 升序
 * - 选中态高亮 + 已加入角标
 * - 单项"加入下载"按钮（直链入队，不做 URL 去重）
 * - Live Photo 检测：items 中存在 live_photo 时显示提示横幅 + 卡片 LIVE 徽章
 *
 * 性能优化：
 * - 去掉 loading="lazy"（横向列表元素少，全部立即加载更流畅）
 * - img 添加 decoding="async" 避免阻塞主线程
 * - 滚动容器添加 contain 隔离重绘范围
 * - img 固定尺寸 + draggable=false 防止布局抖动
 */

import { memo, useCallback, useMemo } from "react";
import { type MediaItem, thumbProxyUrl } from "../../api";
import { useI18n } from "../../i18n";

export interface SortedMediaItem {
  orig_idx: number;       // 原始 items 数组中的索引
  display_pos: number;    // 显示位置（1-based）
  item: MediaItem;
}

interface Props {
  items: SortedMediaItem[];
  selectedItemIndex: number;            // orig_idx，-1 表示未选中
  addedItemIndices: Record<number, boolean>;
  onSelect: (origIdx: number) => void;
  onEnqueue: (origIdx: number) => void;
}

export function MediaItemsList({ items, selectedItemIndex, addedItemIndices, onSelect, onEnqueue }: Props) {
  const { tr } = useI18n();
  // 检测是否含 Live Photo（任一 item.live_photo 非空）
  const hasLivePhoto = useMemo(
    () => items.some((s) => s.item.live_photo),
    [items]
  );

  if (items.length <= 1) return null;

  return (
    <div className="glass-card mb-4 p-4 animate-slide-up">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          {tr("media_items_title")} ({items.length})
        </h3>
        <span className="text-xs text-text-muted">{tr("media_items_hint")}</span>
      </div>

      {/* Live Photo 提示横幅 */}
      {hasLivePhoto && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-accent/25 bg-accent/8 px-3 py-2 text-xs text-text">
          <LiveIcon className="h-3.5 w-3.5 text-accent" />
          <span>{tr("live_photo_banner")}</span>
        </div>
      )}

      {/* 横向滚动容器 — 隔离重绘，避免滚动时影响下方预览区 */}
      <div
        className="flex gap-3 overflow-x-auto pb-2 media-items-scroll"
      >
        {items.map((s) => (
          <MediaItemCard
            key={s.orig_idx}
            sortedItem={s}
            isSelected={s.orig_idx === selectedItemIndex}
            isAdded={!!addedItemIndices[s.orig_idx]}
            isLivePhoto={!!s.item.live_photo}
            onSelect={onSelect}
            onEnqueue={onEnqueue}
          />
        ))}
      </div>
    </div>
  );
}

// ============================================================
// MediaItemCard — 单个素材卡片，memo 包裹避免无关重渲染
// ============================================================

interface CardProps {
  sortedItem: SortedMediaItem;
  isSelected: boolean;
  isAdded: boolean;
  isLivePhoto: boolean;
  onSelect: (origIdx: number) => void;
  onEnqueue: (origIdx: number) => void;
}

/** React.memo 默认浅比较：sortedItem.item 引用不变 + isSelected/isAdded/isLivePhoto 不变 → 跳过渲染
 *  切换 selectedItemIndex 时，只有旧卡片（isSelected: true→false）和新卡片（false→true）重渲染，
 *  其他 N-2 个卡片全部跳过，大幅减少 DOM diff 和 thumbProxyUrl 字符串构建开销。 */
const MediaItemCard = memo(function MediaItemCard({
  sortedItem: s,
  isSelected,
  isAdded,
  isLivePhoto,
  onSelect,
  onEnqueue,
}: CardProps) {
  const { tr } = useI18n();
  // 缩略图 URL 缓存：sortedItem.item.url 不变时复用同一字符串，避免每次 render 重新构建 URLSearchParams
  const thumbSrc = useMemo(
    () => (!s.item.is_video && s.item.url) ? thumbProxyUrl(s.item.url, 200, 200) : "",
    [s.item.is_video, s.item.url]
  );

  const handleClick = useCallback(() => onSelect(s.orig_idx), [onSelect, s.orig_idx]);
  const handleEnqueueClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    onEnqueue(s.orig_idx);
  }, [onEnqueue, s.orig_idx]);

  return (
    <div
      onClick={handleClick}
      className={`group relative flex-shrink-0 cursor-pointer overflow-hidden rounded-xl border ${
        isSelected
          ? "border-accent shadow-lg shadow-accent/20"
          : "border-white/10 hover:border-white/20"
      }`}
      style={{ width: 140, height: 140 }}
    >
      {/* 缩略图 / 视频占位 */}
      {thumbSrc ? (
        <img
          src={thumbSrc}
          alt=""
          width={140}
          height={140}
          decoding="async"
          draggable={false}
          className="h-full w-full select-none object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-bg-elevated">
          <VideoIcon className="h-8 w-8 text-text-muted" />
        </div>
      )}

      {/* 选中态边框（独立绝对定位层，不影响布局） */}
      {isSelected && (
        <div className="pointer-events-none absolute inset-0 ring-2 ring-inset ring-accent" />
      )}

      {/* 已加入角标 */}
      {isAdded && (
        <div className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-success text-white shadow-md">
          <CheckIcon className="h-3 w-3" />
        </div>
      )}

      {/* Live Photo 徽章（左上角，与序号并排） */}
      {isLivePhoto && (
        <div className="absolute left-1 top-1 flex items-center gap-0.5 rounded-full bg-accent/85 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-white backdrop-blur-sm">
          <LiveIcon className="h-2.5 w-2.5" />
          {tr("live_photo_badge")}
        </div>
      )}

      {/* 单项下载按钮（hover 显示） */}
      {!isAdded && (
        <button
          onClick={handleEnqueueClick}
          className="absolute bottom-1 right-1 flex h-7 items-center gap-1 rounded-full bg-accent/90 px-2 text-xs font-medium text-white opacity-0 shadow-md backdrop-blur-sm transition-opacity group-hover:opacity-100 hover:bg-accent"
        >
          {tr("download")}
        </button>
      )}

      {/* 序号（Live Photo 时下移避免重叠） */}
      <div
        className={`absolute right-1 ${isLivePhoto ? "top-7" : "top-1"} rounded-full bg-black/50 px-1.5 py-0.5 text-[10px] font-mono text-white/80 backdrop-blur-sm`}
      >
        #{s.display_pos}
      </div>
    </div>
  );
});

function VideoIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="6" width="14" height="12" rx="2" />
      <path d="M22 8l-6 4 6 4V8z" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

/** Live Photo 图标 — 三道同心弧线表示动态 */
function LiveIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M5.5 5.5a9 9 0 0 0 0 13M18.5 5.5a9 9 0 0 1 0 13M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7" />
    </svg>
  );
}
