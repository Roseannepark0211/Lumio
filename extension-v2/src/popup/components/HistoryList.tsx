/**
 * 历史记录列表
 * - 顶部工具栏：标题 + 多选切换 + 全选/批量删除/清空
 * - 列表：缩略图 + 平台 badge + hover 操作
 */
import { useEffect } from "react";
import { useHistoryStore } from "../store/history";
import { HistoryItemCard } from "./HistoryItemCard";

export function HistoryList() {
  const {
    items,
    loading,
    multiSelectMode,
    selectedIds,
    load,
    setMultiSelectMode,
    selectAll,
    clearSelection,
    deleteSelected,
    clearAll,
  } = useHistoryStore();

  useEffect(() => {
    load();
  }, [load]);

  const hasItems = items.length > 0;
  const selectedCount = selectedIds.size;

  return (
    <div className="glass-card flex-1 overflow-hidden p-3">
      {/* 工具栏 */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            最近发送
          </span>
          {hasItems && (
            <span className="rounded-full bg-text/5 px-2 py-0.5 text-[10px] text-text-dim">
              {items.length}
            </span>
          )}
        </div>

        {hasItems && (
          <div className="flex items-center gap-1">
            {multiSelectMode ? (
              <>
                <button className="btn-ghost" onClick={selectAll}>
                  全选
                </button>
                <button
                  className="btn-ghost"
                  onClick={clearSelection}
                  disabled={selectedCount === 0}
                >
                  取消
                </button>
                <button
                  className="btn-ghost text-danger hover:bg-danger/10"
                  onClick={deleteSelected}
                  disabled={selectedCount === 0}
                >
                  删除{selectedCount > 0 ? ` (${selectedCount})` : ""}
                </button>
                <button
                  className="btn-ghost"
                  onClick={() => setMultiSelectMode(false)}
                >
                  退出
                </button>
              </>
            ) : (
              <>
                <button className="btn-ghost" onClick={() => setMultiSelectMode(true)}>
                  多选
                </button>
                <button
                  className="btn-ghost text-danger hover:bg-danger/10"
                  onClick={() => {
                    if (confirm("确认清空所有历史记录？")) clearAll();
                  }}
                >
                  清空
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* 列表 */}
      <div className="max-h-[280px] overflow-y-auto pr-1">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-8">
            <svg
              className="h-5 w-5 animate-spin text-text-dim"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
              <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
          </div>
        ) : hasItems ? (
          <div className="flex flex-col gap-0.5">
            {items.map((item) => (
              <HistoryItemCard key={item.id} item={item} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-text/5 text-text-dim">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
            </div>
            <p className="text-xs text-text-dim">暂无发送记录</p>
            <p className="mt-1 text-[10px] text-text-dim/60">
              发送页面到 Lumio 后会在这里显示
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
