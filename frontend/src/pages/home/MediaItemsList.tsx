/**
 * HomePage 子组件：Media Items 横向列表（多图/多视频帖的子项切换）。
 *
 * 与 QML 版 HomePage.qml line 378-591 对齐：
 * - 视频项在前、图片在后，按 orig_idx 升序
 * - 选中态高亮 + 已加入角标
 * - 单项"加入下载"按钮（直链入队，不做 URL 去重）
 */

import { type MediaItem, thumbProxyUrl } from "../../api";

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
  if (items.length <= 1) return null;

  return (
    <div className="glass-card mb-4 p-4 animate-slide-up">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          媒体项 ({items.length})
        </h3>
        <span className="text-xs text-text-muted">点击卡片切换预览</span>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {items.map((s) => {
          const isSelected = s.orig_idx === selectedItemIndex;
          const isAdded = !!addedItemIndices[s.orig_idx];
          return (
            <div
              key={s.orig_idx}
              onClick={() => onSelect(s.orig_idx)}
              className={`group relative flex-shrink-0 cursor-pointer overflow-hidden rounded-xl border transition-all ${
                isSelected
                  ? "border-accent shadow-lg shadow-accent/20"
                  : "border-white/10 hover:border-white/20"
              }`}
              style={{ width: 140, height: 140 }}
            >
              {/* 缩略图 / 视频占位 */}
              {!s.item.is_video && s.item.url ? (
                <img
                  src={thumbProxyUrl(s.item.url)}
                  alt=""
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-bg-elevated">
                  <VideoIcon className="h-8 w-8 text-text-muted" />
                </div>
              )}

              {/* 选中态边框 */}
              {isSelected && (
                <div className="pointer-events-none absolute inset-0 ring-2 ring-inset ring-accent" />
              )}

              {/* 已加入角标 */}
              {isAdded && (
                <div className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-success text-white shadow-md">
                  <CheckIcon className="h-3 w-3" />
                </div>
              )}

              {/* 单项下载按钮（hover 显示） */}
              {!isAdded && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onEnqueue(s.orig_idx);
                  }}
                  className="absolute bottom-1 right-1 flex h-7 items-center gap-1 rounded-full bg-accent/90 px-2 text-xs font-medium text-white opacity-0 shadow-md backdrop-blur-sm transition-opacity group-hover:opacity-100 hover:bg-accent"
                >
                  下载
                </button>
              )}

              {/* 序号 */}
              <div className="absolute left-1 top-1 rounded-full bg-black/50 px-1.5 py-0.5 text-[10px] font-mono text-white/80 backdrop-blur-sm">
                #{s.display_pos}
              </div>
            </div>
          );
        })}
      </div>
    </div>
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

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
