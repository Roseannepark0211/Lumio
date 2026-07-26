/**
 * HomePage 子组件：X-Sou 搜索面板（含搜索框、结果列表、分页、多选、批量入队）。
 *
 * 与 QML 版 HomePage.qml line 799-1061 对齐：
 * - 搜索按钮由 config.enable_xsou 控制可见性（HomePage 主组件传入）
 * - @username 在后端自动转 from:username
 * - 搜索结果列表含缩略图、内容、预览、入队按钮
 * - 多选批量入队（video_url 作为 direct_url）
 * - 分页（上一页/下一页）
 */

import { useState } from "react";
import { type XSouResult, thumbProxyUrl } from "../../api";

interface Props {
  isSearching: boolean;
  searchResults: XSouResult[];
  searchTotal: number;
  searchPage: number;
  searchLimit: number;
  selectedItems: Record<number, boolean>;
  onSearch: (query: string, page: number) => void;
  onSelectItem: (idx: number, checked: boolean) => void;
  onClearSelection: () => void;
  onBatchEnqueue: () => void;
  onPreview: (videoUrl: string) => void;
}

export function XSouSearchPanel({
  isSearching,
  searchResults,
  searchTotal,
  searchPage,
  searchLimit,
  selectedItems,
  onSearch,
  onSelectItem,
  onClearSelection,
  onBatchEnqueue,
  onPreview,
}: Props) {
  const [query, setQuery] = useState("");
  const selectedCount = Object.values(selectedItems).filter(Boolean).length;
  const totalPages = Math.ceil(searchTotal / searchLimit) || 1;

  return (
    <div className="glass-card mb-4 p-4 animate-slide-up">
      {/* 搜索框 */}
      <div className="mb-3 flex items-center gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query.trim() && !isSearching) {
              onSearch(query.trim(), 1);
            }
          }}
          placeholder="搜索 X 内容（@username 转 from: 搜索）"
          className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-text placeholder:text-text-muted/60 focus:border-accent focus:outline-none"
        />
        <button
          disabled={!query.trim() || isSearching}
          onClick={() => onSearch(query.trim(), 1)}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-glow disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSearching ? "搜索中..." : "搜索"}
        </button>
      </div>

      {/* 18+ 警告 */}
      <div className="mb-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-1.5 text-xs text-warning">
        ⚠ X-Sou 搜索结果可能含 18+ 内容，仅供个人学习研究使用
      </div>

      {/* 结果列表 */}
      {searchResults.length > 0 && (
        <>
          <div className="mb-2 flex items-center justify-between text-xs text-text-muted">
            <span>共 {searchTotal} 条结果（第 {searchPage}/{totalPages} 页）</span>
            {selectedCount > 0 && (
              <span className="text-accent">已选 {selectedCount} 项</span>
            )}
          </div>

          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
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
                <div className="flex-shrink-0 overflow-hidden rounded-md" style={{ width: 80, height: 80 }}>
                  {r.video_cover ? (
                    <img
                      src={thumbProxyUrl(r.video_cover)}
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
                      预览
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
                onClick={() => onSearch(query.trim(), searchPage - 1)}
                className="rounded-md bg-white/5 px-3 py-1 text-xs text-text hover:bg-white/10 disabled:opacity-30"
              >
                上一页
              </button>
              <button
                disabled={searchPage >= totalPages || isSearching}
                onClick={() => onSearch(query.trim(), searchPage + 1)}
                className="rounded-md bg-white/5 px-3 py-1 text-xs text-text hover:bg-white/10 disabled:opacity-30"
              >
                下一页
              </button>
            </div>
            <div className="flex gap-2">
              {selectedCount > 0 && (
                <button
                  onClick={onClearSelection}
                  className="rounded-md bg-white/5 px-3 py-1 text-xs text-text-muted hover:bg-white/10"
                >
                  取消选择
                </button>
              )}
              <button
                disabled={selectedCount === 0}
                onClick={onBatchEnqueue}
                className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white hover:bg-accent-glow disabled:opacity-30"
              >
                入队 ({selectedCount})
              </button>
            </div>
          </div>
        </>
      )}

      {/* 空状态 */}
      {searchResults.length === 0 && !isSearching && searchPage === 0 && (
        <div className="py-6 text-center text-xs text-text-muted">
          输入关键词开始搜索
        </div>
      )}
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
