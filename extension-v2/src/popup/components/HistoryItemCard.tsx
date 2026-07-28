/**
 * 历史记录单条卡片
 * - 缩略图 + 平台 badge + 标题 + 时间
 * - hover 显示重发/删除
 * - 多选模式下显示 checkbox
 */
import { useState } from "react";
import type { HistoryItem } from "../../types";
import { useHistoryStore } from "../store/history";
import { PLATFORM_LABELS, PLATFORM_COLORS } from "./platform-badge";

interface Props {
  item: HistoryItem;
}

export function HistoryItemCard({ item }: Props) {
  const { multiSelectMode, selectedIds, toggleSelect, deleteItem, resendItem } = useHistoryStore();
  const [action, setAction] = useState<"idle" | "deleting" | "resending">("idle");
  const [feedback, setFeedback] = useState<{ type: "ok" | "err"; msg: string } | null>(null);

  const isSelected = selectedIds.has(item.id);

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setAction("deleting");
    await deleteItem(item.id);
    setAction("idle");
  };

  const handleResend = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setAction("resending");
    const ok = await resendItem(item.id);
    setFeedback({
      type: ok ? "ok" : "err",
      msg: ok ? "已重发 ✓" : "重发失败",
    });
    setAction("idle");
    setTimeout(() => setFeedback(null), 2000);
  };

  const time = new Date(item.time).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      className={`group relative flex cursor-pointer items-center gap-3 rounded-xl p-2 transition-all ${
        isSelected ? "bg-accent/15 ring-1 ring-accent/40" : "hover:bg-text/5"
      }`}
      onClick={() => multiSelectMode && toggleSelect(item.id)}
    >
      {/* 多选 checkbox */}
      {multiSelectMode && (
        <div
          className={`flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border-2 transition-all ${
            isSelected
              ? "border-accent bg-accent text-white"
              : "border-text-muted/40"
          }`}
        >
          {isSelected && (
            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              <path d="M5 13l4 4L19 7" />
            </svg>
          )}
        </div>
      )}

      {/* 缩略图 */}
      <div className="relative h-12 w-12 flex-shrink-0 overflow-hidden rounded-lg bg-text/10">
        {item.thumbnail ? (
          <img
            src={item.thumbnail}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            draggable={false}
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-text-dim">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="9" cy="9" r="2" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
          </div>
        )}
        {/* 平台 badge */}
        {item.platform && (
          <span
            className={`absolute left-0 top-0 rounded-br px-1 py-0.5 text-[8px] font-bold text-white ${PLATFORM_COLORS[item.platform]}`}
          >
            {PLATFORM_LABELS[item.platform]}
          </span>
        )}
      </div>

      {/* 标题 + 时间 */}
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium text-text" title={item.title || item.url}>
          {item.title || item.url}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[10px] text-text-dim">
          <span className="flex-shrink-0">{time}</span>
          {item.author && (
            <span className="truncate" title={`@${item.author}`}>@{item.author}</span>
          )}
        </div>
        {feedback && (
          <div
            className={`mt-1 text-[10px] ${
              feedback.type === "ok" ? "text-success" : "text-danger"
            }`}
          >
            {feedback.msg}
          </div>
        )}
      </div>

      {/* hover 操作按钮 */}
      {!multiSelectMode && (
        <div className="flex flex-shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            className="flex h-6 w-6 items-center justify-center rounded-md bg-text/5 text-text-muted hover:bg-accent/20 hover:text-accent disabled:opacity-40"
            onClick={handleResend}
            disabled={action !== "idle"}
            title="重发"
          >
            {action === "resending" ? (
              <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              </svg>
            ) : (
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M3 12a9 9 0 1 0 9-9" />
                <path d="M3 4v5h5" />
              </svg>
            )}
          </button>
          <button
            className="flex h-6 w-6 items-center justify-center rounded-md bg-text/5 text-text-muted hover:bg-danger/20 hover:text-danger disabled:opacity-40"
            onClick={handleDelete}
            disabled={action !== "idle"}
            title="删除"
          >
            {action === "deleting" ? (
              <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              </svg>
            ) : (
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M3 6h18" />
                <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              </svg>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
