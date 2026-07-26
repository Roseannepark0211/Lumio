/**
 * React InboxPage — 复刻 QML InboxPage.qml 完整功能。
 *
 * 功能清单（与 QML 版本对齐）：
 *   1. 收件箱列表（缩略图 + 标题 + 作者/平台/来源/时间 + 状态徽章 + 操作按钮）
 *   2. 状态筛选（all/new/queued/downloaded/archived/failed）+ 来源筛选（all/browser/telegram/manual）
 *   3. 单条操作：下载 / 打开原网页 / 归档 / 删除（带确认对话框）
 *   4. 批量模式：选择 / 全选 / 取消全选 / 批量下载 / 批量删除
 *   5. 清空已完成（downloaded/archived）— 带确认对话框
 *   6. WebSocket 事件驱动刷新（inbox_changed）
 *   7. 空状态提示
 *
 * 与 QML 版本差异：
 *   - 字段名 type / captured_at（FastAPI 包装层映射自 InboxItem 模型）
 *   - QML 用 Dialog，React 用 ModalDialog 组件（与 HistoryPage 同款）
 *   - 状态/来源下拉暂用原生 <select>（与 HistoryPage 同款风格）
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import {
  api,
  subscribeEvents,
  thumbProxyUrl,
  type AppEvent,
  type InboxItem,
} from "../api";

// ============================================================
// 常量
// ============================================================

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "new", label: "新内容" },
  { value: "queued", label: "已入队" },
  { value: "downloaded", label: "已下载" },
  { value: "archived", label: "已归档" },
  { value: "failed", label: "失败" },
];

const SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "全部来源" },
  { value: "browser", label: "浏览器扩展" },
  { value: "telegram", label: "Telegram" },
  { value: "manual", label: "手动添加" },
];

function sourceLabel(s: string): string {
  switch (s) {
    case "browser":
      return "浏览器扩展";
    case "telegram":
      return "Telegram";
    case "manual":
      return "手动添加";
    default:
      return s || "—";
  }
}

function statusLabel(s: string): string {
  switch (s) {
    case "new":
      return "新内容";
    case "queued":
      return "已入队";
    case "downloaded":
      return "已下载";
    case "archived":
      return "已归档";
    case "failed":
      return "失败";
    default:
      return s;
  }
}

/** 状态徽章颜色（与 QML Badge.status 映射对齐） */
function statusBadgeClass(s: string): { bg: string; text: string; border: string } {
  switch (s) {
    case "downloaded":
      return {
        bg: "bg-success/10",
        text: "text-success",
        border: "border-success/30",
      };
    case "failed":
      return {
        bg: "bg-danger/10",
        text: "text-danger",
        border: "border-danger/30",
      };
    case "queued":
      return {
        bg: "bg-warning/10",
        text: "text-warning",
        border: "border-warning/30",
      };
    case "archived":
      return {
        bg: "bg-white/5",
        text: "text-text-muted",
        border: "border-white/10",
      };
    case "new":
    default:
      return {
        bg: "bg-accent/10",
        text: "text-accent",
        border: "border-accent/30",
      };
  }
}

function platformLabel(p: string): string {
  if (!p) return "—";
  switch (p) {
    case "youtube":
      return "YouTube";
    case "instagram":
      return "IG";
    case "x":
      return "X";
    case "bilibili":
      return "B站";
    case "douyin":
      return "抖音";
    case "kuaishou":
      return "快手";
    case "weibo":
      return "微博";
    case "xiaohongshu":
      return "小红书";
    case "telegram":
      return "Telegram";
    default:
      return p.toUpperCase();
  }
}

/** 平台图标色（与 QML Theme.platformColor 对齐） */
function platformIconColor(p: string): string {
  switch (p) {
    case "youtube":
      return "text-red-400";
    case "instagram":
      return "text-pink-400";
    case "x":
      return "text-zinc-200";
    case "bilibili":
      return "text-blue-400";
    case "douyin":
      return "text-zinc-100";
    case "kuaishou":
      return "text-orange-400";
    case "weibo":
      return "text-orange-500";
    case "xiaohongshu":
      return "text-red-500";
    case "telegram":
      return "text-sky-400";
    default:
      return "text-text-muted";
  }
}

function formatTime(t: string): string {
  if (!t || t.length === 0) return "—";
  // ISO "2026-07-27T08:30:00" → "2026-07-27 08:30:00"
  return t.replace("T", " ").substring(0, 19);
}

// ============================================================
// 主组件
// ============================================================

export function InboxPage() {
  // —— 数据状态 ——
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // —— 筛选状态（与 QML root 属性对齐） ——
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterSource, setFilterSource] = useState("all");

  // —— 批量选择 ——
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // —— 对话框 ——
  const [deleteDialogIds, setDeleteDialogIds] = useState<string[] | null>(null);
  const [clearDialogOpen, setClearDialogOpen] = useState(false);

  // —— 拉取数据 ——
  const reload = useCallback(async () => {
    try {
      const r = await api.getInbox();
      setItems(r);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // —— 初次加载 ——
  useEffect(() => {
    reload();
  }, [reload]);

  // —— WebSocket 事件订阅 ——
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      if (e.type === "inbox_changed") {
        reload();
      }
    });
    return unsub;
  }, [reload]);

  // —— 客户端筛选（与 QML _applyFilter 对齐） ——
  const filtered = useMemo(() => {
    return items.filter((it) => {
      if (filterStatus !== "all" && it.status !== filterStatus) return false;
      if (filterSource !== "all" && it.source !== filterSource) return false;
      return true;
    });
  }, [items, filterStatus, filterSource]);

  // —— 统计 ——
  const newCount = useMemo(
    () => items.filter((it) => it.status === "new").length,
    [items]
  );

  // —— 选择操作 ——
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }, []);

  const selectAll = useCallback(() => {
    setSelectedIds(filtered.map((it) => it.id));
  }, [filtered]);

  const deselectAll = useCallback(() => {
    setSelectedIds([]);
  }, []);

  // —— 单条操作 ——
  const onDownload = useCallback(async (itemId: string) => {
    try {
      await api.inboxDownload(itemId);
      // 后端会推 inbox_changed 事件触发 reload
    } catch (e) {
      console.warn("inbox download failed:", e);
    }
  }, []);

  const onArchive = useCallback(async (itemId: string) => {
    try {
      await api.inboxArchive(itemId);
    } catch (e) {
      console.warn("inbox archive failed:", e);
    }
  }, []);

  const onOpenExternalUrl = useCallback(async (url: string) => {
    if (!url) return;
    try {
      await api.openExternalUrl(url);
    } catch (e) {
      console.warn("open external url failed:", e);
    }
  }, []);

  const onSingleDelete = useCallback((itemId: string) => {
    setDeleteDialogIds([itemId]);
  }, []);

  // —— 批量操作 ——
  const onBatchDownload = useCallback(async () => {
    if (selectedIds.length === 0) return;
    try {
      await api.inboxBatchDownload(selectedIds);
      setSelectedIds([]);
      setSelectMode(false);
    } catch (e) {
      console.warn("inbox batch download failed:", e);
    }
  }, [selectedIds]);

  const onBatchDelete = useCallback(() => {
    if (selectedIds.length === 0) return;
    setDeleteDialogIds(selectedIds.slice());
  }, [selectedIds]);

  // —— 对话框确认 ——
  const onConfirmDelete = useCallback(async () => {
    const ids = deleteDialogIds;
    setDeleteDialogIds(null);
    if (!ids || ids.length === 0) return;
    try {
      if (ids.length === 1) {
        await api.inboxDelete(ids[0]);
      } else {
        await api.inboxBatchDelete(ids);
      }
      setSelectedIds([]);
    } catch (e) {
      console.warn("inbox delete failed:", e);
    }
  }, [deleteDialogIds]);

  const onConfirmClear = useCallback(async () => {
    setClearDialogOpen(false);
    try {
      await api.inboxClearCompleted();
    } catch (e) {
      console.warn("inbox clear completed failed:", e);
    }
  }, []);

  // —— 渲染 ——
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-text-muted">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="glass-card max-w-md p-6">
          <h2 className="text-lg font-semibold text-danger">加载失败</h2>
          <p className="mt-2 text-sm text-text-muted">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="flex flex-col gap-4 p-6">
        {/* PageHeader */}
        <header className="flex animate-slide-up items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-text">收件箱</h1>
            <p className="mt-0.5 text-xs text-text-muted">
              浏览器扩展 / Telegram Bot 采集的内容，可批量下载或归档
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* 计数 badge */}
            <div className="rounded-full border border-accent/30 bg-accent/15 px-2.5 py-1 text-xs font-semibold text-accent">
              {newCount} 新 · {items.length} 条
            </div>
            {/* 刷新 */}
            <button
              onClick={() => reload()}
              className="flex items-center gap-1.5 rounded-lg bg-white/5 px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
              title="刷新"
            >
              ↻ 刷新
            </button>
            {/* 批量选择切换 */}
            <button
              onClick={() => {
                setSelectMode((v) => !v);
                if (selectMode) setSelectedIds([]);
              }}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                selectMode
                  ? "bg-accent/20 text-accent hover:bg-accent/30"
                  : "bg-white/5 text-text-muted hover:bg-white/10 hover:text-text"
              }`}
              title={selectMode ? "退出批量选择" : "批量选择"}
            >
              {selectMode ? "✕ 取消选择" : "☑ 批量选择"}
            </button>
            {/* 清空已完成 */}
            <button
              onClick={() => setClearDialogOpen(true)}
              disabled={items.length === 0}
              className="flex items-center gap-1.5 rounded-lg bg-danger/10 px-3 py-1.5 text-xs font-medium text-danger transition-colors hover:bg-danger/20 disabled:opacity-40 disabled:hover:bg-danger/10"
              title="清空已下载/已归档"
            >
              🗑 清空已完成
            </button>
          </div>
        </header>

        {/* 批量操作栏（仅 selectMode 显示） */}
        {selectMode && (
          <div className="glass-card flex animate-slide-up items-center gap-3 px-3.5 py-2.5">
            <span className="text-xs text-text-muted">
              {selectedIds.length > 0
                ? `已选 ${selectedIds.length} 项`
                : "未选择任何项"}
            </span>
            <div className="flex-1" />
            <button
              onClick={selectAll}
              className="rounded-lg bg-white/5 px-2.5 py-1 text-xs text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              全选
            </button>
            <button
              onClick={deselectAll}
              disabled={selectedIds.length === 0}
              className="rounded-lg bg-white/5 px-2.5 py-1 text-xs text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-40"
            >
              取消全选
            </button>
            <button
              onClick={onBatchDownload}
              disabled={selectedIds.length === 0}
              className="flex items-center gap-1 rounded-lg bg-accent/15 px-2.5 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/25 disabled:opacity-40 disabled:hover:bg-accent/15"
            >
              ↓ 批量下载
            </button>
            <button
              onClick={onBatchDelete}
              disabled={selectedIds.length === 0}
              className="flex items-center gap-1 rounded-lg bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/20 disabled:opacity-40 disabled:hover:bg-danger/10"
            >
              🗑 批量删除
            </button>
          </div>
        )}

        {/* Filter bar */}
        <div className="glass-card flex items-center gap-2.5 px-3.5 py-2.5">
          <span className="text-xs text-text-muted">状态</span>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="w-36 rounded-lg border border-white/5 bg-white/5 px-3 py-1.5 text-sm text-text focus:border-accent/50 focus:outline-none"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-zinc-900">
                {o.label}
              </option>
            ))}
          </select>
          <div className="flex-1" />
          <span className="text-xs text-text-muted">来源</span>
          <select
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
            className="w-36 rounded-lg border border-white/5 bg-white/5 px-3 py-1.5 text-sm text-text focus:border-accent/50 focus:outline-none"
          >
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-zinc-900">
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* 空状态 */}
        {items.length === 0 && (
          <div className="mt-20 text-center text-sm text-text-muted">
            收件箱为空
          </div>
        )}

        {/* 筛选后无结果 */}
        {items.length > 0 && filtered.length === 0 && (
          <div className="mt-20 text-center text-sm text-text-muted">
            没有匹配的条目
          </div>
        )}

        {/* 收件箱列表 */}
        {filtered.length > 0 && (
          <div className="flex flex-col gap-2">
            {filtered.map((it) => (
              <InboxCard
                key={it.id}
                item={it}
                selectMode={selectMode}
                selected={selectedIds.includes(it.id)}
                onToggleSelect={toggleSelect}
                onDownload={onDownload}
                onArchive={onArchive}
                onOpenExternalUrl={onOpenExternalUrl}
                onDelete={onSingleDelete}
              />
            ))}
          </div>
        )}

        {/* 底部 spacer */}
        <div className="h-12" />
      </div>

      {/* 删除确认对话框 */}
      {deleteDialogIds && (
        <ModalDialog
          title="删除收件箱条目"
          onClose={() => setDeleteDialogIds(null)}
        >
          <p className="text-sm text-text">
            确定要删除 {deleteDialogIds.length} 条收件箱条目吗？此操作不可撤销。
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setDeleteDialogIds(null)}
              className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              取消
            </button>
            <button
              onClick={onConfirmDelete}
              className="rounded-lg bg-danger px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger-glow"
            >
              删除
            </button>
          </div>
        </ModalDialog>
      )}

      {/* 清空已完成对话框 */}
      {clearDialogOpen && (
        <ModalDialog
          title="清空已完成的收件箱条目"
          onClose={() => setClearDialogOpen(false)}
        >
          <p className="text-sm text-text">
            确定要清空所有 <span className="font-semibold text-success">已下载</span> 和{" "}
            <span className="font-semibold text-text-muted">已归档</span> 的收件箱条目吗？
          </p>
          <p className="mt-1 text-xs text-text-muted">
            注意：仅清理收件箱记录，不会删除已下载的文件。
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setClearDialogOpen(false)}
              className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              取消
            </button>
            <button
              onClick={onConfirmClear}
              className="rounded-lg bg-danger px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger-glow"
            >
              清空
            </button>
          </div>
        </ModalDialog>
      )}
    </div>
  );
}

// ============================================================
// 子组件
// ============================================================

interface InboxCardProps {
  item: InboxItem;
  selectMode: boolean;
  selected: boolean;
  onToggleSelect: (id: string) => void;
  onDownload: (id: string) => void;
  onArchive: (id: string) => void;
  onOpenExternalUrl: (url: string) => void;
  onDelete: (id: string) => void;
}

function InboxCard({
  item,
  selectMode,
  selected,
  onToggleSelect,
  onDownload,
  onArchive,
  onOpenExternalUrl,
  onDelete,
}: InboxCardProps) {
  const hasThumb = !!item.thumbnail_url && item.thumbnail_url.length > 0;
  const canDownload = item.status === "new" || item.status === "failed";
  const canArchive = item.status !== "archived";
  const isImage = item.type === "image";

  const badge = statusBadgeClass(item.status);

  return (
    <div className="glass-card flex items-center gap-3.5 p-3.5">
      {/* 选择框（仅 selectMode 显示） */}
      {selectMode && (
        <button
          onClick={() => onToggleSelect(item.id)}
          className={`flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-md border transition-colors ${
            selected
              ? "border-accent bg-accent text-white"
              : "border-white/15 bg-transparent text-transparent hover:border-accent/50"
          }`}
          title={selected ? "取消选择" : "选择"}
        >
          ✓
        </button>
      )}

      {/* Thumbnail / 平台图标 */}
      <div className="relative h-[62px] w-[62px] shrink-0 overflow-hidden rounded-xl border border-white/10 bg-black/30">
        {hasThumb ? (
          <img
            src={thumbProxyUrl(item.thumbnail_url)}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div
            className={`flex h-full w-full items-center justify-center text-xl ${
              isImage ? "text-text-muted" : platformIconColor(item.platform)
            }`}
          >
            {isImage ? "🖼" : "▶"}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="truncate text-sm font-semibold text-text">
          {item.title || item.url}
        </div>
        <div className="truncate font-mono text-xs text-text-muted">
          {item.author || "—"}
          {" · "}
          {platformLabel(item.platform)}
          {" · "}
          {sourceLabel(item.source)}
          {" · "}
          {formatTime(item.captured_at)}
        </div>
        {/* 失败原因 */}
        {item.status === "failed" && item.error_message && (
          <div className="truncate text-xs text-danger">
            ⚠ {item.error_message}
          </div>
        )}
      </div>

      {/* 状态徽章 */}
      <div
        className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold ${badge.bg} ${badge.text} ${badge.border}`}
      >
        {statusLabel(item.status)}
      </div>

      {/* Actions */}
      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={() => onDownload(item.id)}
          disabled={!canDownload}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-accent/10 hover:text-accent disabled:opacity-30 disabled:hover:bg-transparent"
          title={canDownload ? "下载" : "当前状态不可下载"}
        >
          ↓
        </button>
        <button
          onClick={() => onOpenExternalUrl(item.url)}
          disabled={!item.url}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
          title="打开原网页"
        >
          ↗
        </button>
        <button
          onClick={() => onArchive(item.id)}
          disabled={!canArchive}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
          title={canArchive ? "归档" : "已归档"}
        >
          📦
        </button>
        <button
          onClick={() => onDelete(item.id)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-danger/10 hover:text-danger"
          title="删除"
        >
          🗑
        </button>
      </div>
    </div>
  );
}

// 简易模态对话框（替代 QML Dialog，与 HistoryPage 同款）
function ModalDialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="glass-card w-[420px] max-w-[90vw] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-base font-semibold text-text">{title}</h2>
        {children}
      </div>
    </div>
  );
}
