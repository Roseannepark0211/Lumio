/**
 * HomePage 子组件：X-Sou 搜索结果区（嵌入 URL 卡片内部）。
 *
 * V2 重构：搜索输入与按钮已上移到 HomePage 的 URL 操作行，
 * 本组件只负责渲染搜索结果列表、分页、多选、批量入队。
 *
 * 与 QML 版 HomePage.qml line 799-1061 对齐：
 * - @username 在后端自动转 from:username
 * - 搜索结果列表含缩略图、内容、预览、入队按钮
 * - 多选批量入队（video_url 作为 direct_url）
 * - 分页（上一页/下一页）
 */

import { type XSouResult, thumbProxyUrl } from "../../api";
import { useI18n } from "../../i18n";

interface Props {
  searchResults: XSouResult[];
  searchTotal: number;
  searchPage: number;
  searchLimit: number;
  selectedItems: Record<number, boolean>;
  isSearching: boolean;
  onSelectItem: (idx: number, checked: boolean) => void;
  onClearSelection: () => void;
  onBatchEnqueue: () => void;
  onPreview: (videoUrl: string) => void;
  onPageChange: (page: number) => void;
  onClose: () => void;
}

export function XSouSearchPanel({
  searchResults,
  searchTotal,
  searchPage,
  searchLimit,
  selectedItems,
  isSearching,
  onSelectItem,
  onClearSelection,
  onBatchEnqueue,
  onPreview,
  onPageChange,
  onClose,
}: Props) {
  const { tr } = useI18n();
  const selectedCount = Object.values(selectedItems).filter(Boolean).length;
  const totalPages = Math.ceil(searchTotal / searchLimit) || 1;

  // 无结果且非搜索中：不渲染（避免空块挤占 URL 卡片空间）
  if (searchResults.length === 0 && !isSearching) return null;

  return (
    <div className="mt-4 border-t border-white/8 pt-4 animate-fade-in">
      {/* 头部：结果统计 + 关闭按钮 */}
      <div className="mb-2 flex items-center justify-between text-xs text-text-muted">
        <span>
          {isSearching
            ? tr("search_loading")
            : tr("search_results_total", {
                total: searchTotal,
                page: searchPage,
                pages: totalPages,
              })}
          {selectedCount > 0 && (
            <span className="ml-2 text-accent">
              {tr("search_selected_count", { n: selectedCount })}
            </span>
          )}
        </span>
        <button
          onClick={onClose}
          title={tr("close_search_results")}
          className="flex h-6 w-6 items-center justify-center rounded-md bg-white/5 text-text-muted transition-colors hover:bg-white/10 hover:text-text"
        >
          ✕
        </button>
      </div>

      {/* 结果列表 */}
      <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
        {searchResults.map((r, idx) => (
          <div
            key={idx}
            className="flex gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-2 hover:border-white/10"
          >
            {/* 多选 checkbox */}
            <input
              type="checkbox"
              checked={!!selectedItems[idx]}
              onChange={(e) => onSelectItem(idx, e.target.checked)}
              className="mt-1 h-4 w-4 flex-shrink-0 accent-accent"
            />

            {/* 缩略图 */}
            <div
              className="flex-shrink-0 overflow-hidden rounded-md"
              style={{ width: 80, height: 80 }}
            >
              {r.video_cover ? (
                <img
                  src={thumbProxyUrl(r.video_cover, 200, 200)}
                  alt=""
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-bg-elevated text-text-muted">
                  <VideoIcon className="h-5 w-5" />
                </div>
              )}
            </div>

            {/* 内容 */}
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="line-clamp-2 text-xs text-text">{r.content}</div>
              {r.author && (
                <div className="mt-1 text-[10px] text-text-muted">@{r.author}</div>
              )}
              <div className="mt-auto flex gap-1.5 pt-1">
                <button
                  onClick={() => r.video_url && onPreview(r.video_url)}
                  disabled={!r.video_url}
                  className="rounded-md bg-white/5 px-2 py-0.5 text-[10px] text-text hover:bg-white/10 disabled:opacity-30"
                >
                  {tr("preview")}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 分页 + 批量操作 */}
      <div className="mt-3 flex items-center justify-between">
        <div className="flex gap-2">
          <button
            disabled={searchPage <= 1 || isSearching}
            onClick={() => onPageChange(searchPage - 1)}
            className="rounded-md bg-white/5 px-3 py-1 text-xs text-text hover:bg-white/10 disabled:opacity-30"
          >
            {tr("prev_page")}
          </button>
          <button
            disabled={searchPage >= totalPages || isSearching}
            onClick={() => onPageChange(searchPage + 1)}
            className="rounded-md bg-white/5 px-3 py-1 text-xs text-text hover:bg-white/10 disabled:opacity-30"
          >
            {tr("next_page")}
          </button>
        </div>
        <div className="flex gap-2">
          {selectedCount > 0 && (
            <button
              onClick={onClearSelection}
              className="rounded-md bg-white/5 px-3 py-1 text-xs text-text-muted hover:bg-white/10"
            >
              {tr("clear_selection")}
            </button>
          )}
          <button
            disabled={selectedCount === 0}
            onClick={onBatchEnqueue}
            className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white hover:bg-accent-glow disabled:opacity-30"
          >
            {tr("enqueue_count", { n: selectedCount })}
          </button>
        </div>
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
