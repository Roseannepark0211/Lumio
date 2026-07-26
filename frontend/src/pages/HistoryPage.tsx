/**
 * React HistoryPage — 复刻 QML HistoryPage.qml 完整功能。
 *
 * 功能清单（与 QML 版本对齐）：
 *   1. 记录列表（拉取 + 客户端搜索 + 平台筛选）
 *   2. 单条删除 / 清空全部（带确认对话框）
 *   3. 打开文件 / 打开所在目录（source="history" 触发 file_missing 检测）
 *   4. WebSocket 事件驱动刷新（history_changed）
 *   5. file_missing 事件 → 弹对话框 → 确认删除该条记录
 *   6. 空状态提示
 *
 * 与 QML 版本差异：
 *   - 字段名 id（FastAPI 包装层映射自 HistoryRecord.record_id）
 *   - 平台筛选下拉暂用原生 <select>（DownloadsPage 同款风格）
 */

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  api,
  subscribeEvents,
  thumbProxyUrl,
  type AppEvent,
  type HistoryRecord,
} from "../api";

// 平台筛选选项（与 QML HistoryPage.qml model 对齐）
const PLATFORM_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "全部平台" },
  { value: "youtube", label: "YouTube" },
  { value: "instagram", label: "Instagram" },
  { value: "x", label: "X" },
  { value: "bilibili", label: "B站" },
  { value: "douyin", label: "抖音" },
  { value: "kuaishou", label: "快手" },
  { value: "weibo", label: "微博" },
  { value: "xiaohongshu", label: "小红书" },
];

// 平台展示名（平台 key → 用户可见名）
const PLATFORM_LABEL: Record<string, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
  x: "X",
  bilibili: "B站",
  douyin: "抖音",
  kuaishou: "快手",
  weibo: "微博",
  xiaohongshu: "小红书",
};

function platformLabel(p: string): string {
  return PLATFORM_LABEL[p] || (p ? p.toUpperCase() : "—");
}

function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return "—";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function formatTime(t: string): string {
  if (!t || t.length === 0) return "—";
  // ISO "2026-07-27T08:30:00" → "2026-07-27 08:30:00"
  return t.replace("T", " ").substring(0, 19);
}

export function HistoryPage() {
  // —— 数据状态 ——
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [searchText, setSearchText] = useState("");
  const [filterPlatform, setFilterPlatform] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // —— 对话框状态 ——
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [fileMissing, setFileMissing] = useState<{
    path: string;
    recordId: string;
  } | null>(null);

  // 在事件回调中引用最新 records，避免闭包陈旧
  const recordsRef = useRef<HistoryRecord[]>([]);
  recordsRef.current = records;

  // —— 拉取记录 ——
  const reload = useCallback(async () => {
    try {
      const r = await api.getHistory();
      setRecords(r);
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
      switch (e.type) {
        case "history_changed":
        case "history_record_added":
          reload();
          break;

        case "file_missing": {
          // 文件被外部删除 → 弹「是否删除本条记录」对话框
          const p = e.data as
            | { path?: string; source?: string }
            | null;
          if (!p || p.source !== "history" || !p.path) break;
          // 反查 record_id（用 file_path 匹配）
          const rec = recordsRef.current.find(
            (r) => r.file_path === p.path
          );
          setFileMissing({
            path: p.path,
            recordId: rec?.id || "",
          });
          break;
        }

        default:
          break;
      }
    });
    return unsub;
  }, [reload]);

  // —— 客户端搜索 + 平台筛选（与 QML _applyFilter 对齐） ——
  const filtered = useMemo(() => {
    const q = searchText.toLowerCase();
    const fp = filterPlatform;
    return records.filter((r) => {
      if (fp !== "all" && r.platform !== fp) return false;
      if (q.length > 0) {
        const hay = (
          (r.title || "") +
          " " +
          (r.author || "") +
          " " +
          (r.url || "") +
          " " +
          (r.file_path || "")
        ).toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
  }, [records, searchText, filterPlatform]);

  // —— 单条操作 ——
  const onDelete = useCallback(async (id: string) => {
    try {
      await api.deleteHistory(id);
      // 后端会推 history_changed 事件触发 reload，这里不主动刷新
    } catch (e) {
      console.warn("delete history failed:", e);
    }
  }, []);

  const onOpenFile = useCallback(async (path: string) => {
    try {
      await api.openFile(path, "history");
    } catch (e) {
      console.warn("open file failed:", e);
    }
  }, []);

  const onOpenFolder = useCallback(async (path: string) => {
    try {
      await api.openFolder(path, "history");
    } catch (e) {
      console.warn("open folder failed:", e);
    }
  }, []);

  const onClear = useCallback(async () => {
    setConfirmClearOpen(false);
    try {
      await api.clearHistory();
    } catch (e) {
      console.warn("clear history failed:", e);
    }
  }, []);

  const onConfirmFileMissingDelete = useCallback(async () => {
    const id = fileMissing?.recordId;
    setFileMissing(null);
    if (id) {
      try {
        await api.deleteHistory(id);
      } catch (e) {
        console.warn("delete missing-record failed:", e);
      }
    }
  }, [fileMissing]);

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
            <h1 className="text-xl font-bold text-text">下载历史</h1>
            <p className="mt-0.5 text-xs text-text-muted">
              查看历史下载记录、打开文件、清理记录
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* 记录数 badge */}
            <div className="rounded-full border border-accent/30 bg-accent/15 px-2.5 py-1 text-xs font-semibold text-accent">
              {records.length} 条
            </div>
            {/* 清空按钮 */}
            <button
              onClick={() => setConfirmClearOpen(true)}
              disabled={records.length === 0}
              className="flex items-center gap-1.5 rounded-lg bg-danger/10 px-3 py-1.5 text-xs font-medium text-danger transition-colors hover:bg-danger/20 disabled:opacity-40 disabled:hover:bg-danger/10"
              title="清空全部记录"
            >
              🗑 清空
            </button>
          </div>
        </header>

        {/* Filter bar */}
        <div className="glass-card flex items-center gap-2.5 px-3.5 py-2.5">
          <input
            type="text"
            placeholder="搜索标题/作者/URL/文件路径..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="flex-1 rounded-lg border border-white/5 bg-white/5 px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
          />
          <select
            value={filterPlatform}
            onChange={(e) => setFilterPlatform(e.target.value)}
            className="w-40 rounded-lg border border-white/5 bg-white/5 px-3 py-1.5 text-sm text-text focus:border-accent/50 focus:outline-none"
          >
            {PLATFORM_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-zinc-900">
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* 空状态 */}
        {records.length === 0 && (
          <div className="mt-20 text-center text-sm text-text-muted">
            暂无下载记录
          </div>
        )}

        {/* 筛选后无结果（区别于完全空） */}
        {records.length > 0 && filtered.length === 0 && (
          <div className="mt-20 text-center text-sm text-text-muted">
            没有匹配的记录
          </div>
        )}

        {/* 记录列表 */}
        {filtered.length > 0 && (
          <div className="flex flex-col gap-2">
            {filtered.map((r) => (
              <RecordCard
                key={r.id}
                record={r}
                onDelete={onDelete}
                onOpenFile={onOpenFile}
                onOpenFolder={onOpenFolder}
              />
            ))}
          </div>
        )}

        {/* 底部 spacer */}
        <div className="h-12" />
      </div>

      {/* 清空确认对话框 */}
      {confirmClearOpen && (
        <ModalDialog
          title="清空下载历史"
          onClose={() => setConfirmClearOpen(false)}
        >
          <p className="text-sm text-text">
            确定要清空所有下载历史记录吗？此操作不可撤销。
          </p>
          <p className="mt-1 text-xs text-text-muted">
            注意：仅删除历史记录，不会删除已下载的文件。
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setConfirmClearOpen(false)}
              className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              取消
            </button>
            <button
              onClick={onClear}
              className="rounded-lg bg-danger px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger-glow"
            >
              清空
            </button>
          </div>
        </ModalDialog>
      )}

      {/* 文件缺失对话框 */}
      {fileMissing && (
        <ModalDialog
          title="文件缺失"
          onClose={() => setFileMissing(null)}
        >
          <p className="text-sm font-semibold text-danger">
            文件已被外部删除或移动
          </p>
          <p className="mt-2 text-xs text-text">
            是否删除这条历史记录？
          </p>
          <p
            className="mt-2 break-all rounded-md bg-white/5 px-2 py-1.5 font-mono text-[10px] text-text-dim"
          >
            {fileMissing.path}
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setFileMissing(null)}
              className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              取消
            </button>
            <button
              onClick={onConfirmFileMissingDelete}
              disabled={!fileMissing.recordId}
              className="rounded-lg bg-danger px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger-glow disabled:opacity-40"
            >
              删除记录
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

interface RecordCardProps {
  record: HistoryRecord;
  onDelete: (id: string) => void;
  onOpenFile: (path: string) => void;
  onOpenFolder: (path: string) => void;
}

function RecordCard({
  record,
  onDelete,
  onOpenFile,
  onOpenFolder,
}: RecordCardProps) {
  const hasThumb = !!record.thumbnail_url && record.thumbnail_url.length > 0;
  const hasFile = !!record.file_path && record.file_path.length > 0;

  return (
    <div className="glass-card flex items-center gap-3.5 p-3.5">
      {/* Thumbnail / platform icon */}
      <div className="relative h-[62px] w-[62px] shrink-0 overflow-hidden rounded-xl border border-white/10 bg-black/30">
        {hasThumb ? (
          <img
            src={thumbProxyUrl(record.thumbnail_url)}
            alt=""
            className="h-full w-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-lg text-white/60">
            📁
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="truncate text-sm font-semibold text-text">
          {record.title || record.url}
        </div>
        <div className="truncate font-mono text-xs text-text-muted">
          {record.author || ""}
          {record.author ? " · " : ""}
          {platformLabel(record.platform)}
          {" · "}
          <span className="text-[#a8c7ff]">{formatSize(record.file_size)}</span>
          {" · "}
          {formatTime(record.download_time)}
        </div>
        {/* 失败原因 */}
        {!record.success && record.error && (
          <div className="truncate text-xs text-danger">
            ⚠ {record.error}
          </div>
        )}
      </div>

      {/* 状态 Badge */}
      <div
        className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold ${
          record.success
            ? "border-success/30 bg-success/10 text-success"
            : "border-danger/30 bg-danger/10 text-danger"
        }`}
      >
        {record.success ? "完成" : "失败"}
      </div>

      {/* Actions */}
      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={() => onOpenFile(record.file_path)}
          disabled={!hasFile}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
          title="打开文件"
        >
          ▶
        </button>
        <button
          onClick={() => onOpenFolder(record.file_path)}
          disabled={!hasFile}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
          title="打开所在目录"
        >
          📂
        </button>
        <button
          onClick={() => onDelete(record.id)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-danger/10 hover:text-danger"
          title="删除记录"
        >
          🗑
        </button>
      </div>
    </div>
  );
}

// 简易模态对话框（替代 QML Dialog）
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
