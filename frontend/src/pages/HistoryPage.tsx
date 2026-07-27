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
import { useI18n } from "../i18n";

// 平台筛选选项（与 QML HistoryPage.qml model 对齐）
// translate=true 表示 label 字段是 i18n key，需在渲染时用 tr() 解析
const PLATFORM_OPTIONS: { value: string; label: string; translate?: boolean }[] = [
  { value: "all", label: "history_filter_all", translate: true },
  { value: "youtube", label: "YouTube" },
  { value: "instagram", label: "Instagram" },
  { value: "x", label: "X" },
  { value: "bilibili", label: "platform_bilibili", translate: true },
  { value: "douyin", label: "platform_douyin", translate: true },
  { value: "kuaishou", label: "platform_kuaishou", translate: true },
  { value: "weibo", label: "platform_weibo", translate: true },
  { value: "xiaohongshu", label: "platform_xiaohongshu", translate: true },
];

// 平台展示名（平台 key → i18n key 或英文原名）
const PLATFORM_LABEL: Record<string, { text: string; translate?: boolean }> = {
  youtube: { text: "YouTube" },
  instagram: { text: "Instagram" },
  x: { text: "X" },
  bilibili: { text: "platform_bilibili", translate: true },
  douyin: { text: "platform_douyin", translate: true },
  kuaishou: { text: "platform_kuaishou", translate: true },
  weibo: { text: "platform_weibo", translate: true },
  xiaohongshu: { text: "platform_xiaohongshu", translate: true },
};

function platformLabel(p: string, tr: (k: string) => string): string {
  if (!p) return "—";
  const entry = PLATFORM_LABEL[p];
  if (!entry) return p.toUpperCase();
  return entry.translate ? tr(entry.text) : entry.text;
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
  const { tr } = useI18n();
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
        case "history_record_added": {
          // 增量 append：后端携带完整 HistoryRecord 字典
          const newRec = e.data as HistoryRecord | null;
          if (newRec && newRec.id) {
            setRecords((prev) => {
              if (prev.some((x) => x.id === newRec.id)) return prev;
              return [newRec, ...prev];
            });
          } else {
            reload();
          }
          break;
        }
        case "history_changed":
          // 删除/清空 → 全量刷新
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
        <div className="text-text-muted">{tr("loading")}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="glass-card max-w-md p-6">
          <h2 className="text-lg font-semibold text-danger">{tr("load_failed")}</h2>
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
            <h1 className="text-xl font-bold text-text">{tr("history_title")}</h1>
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
              🗑 {tr("history_clear")}
            </button>
          </div>
        </header>

        {/* Filter bar */}
        <div className="glass-card flex items-center gap-2.5 px-3.5 py-2.5">
          <input
            type="text"
            placeholder={tr("history_search")}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="flex-1 rounded-lg border border-text/15 bg-bg-surface px-3 py-1.5 text-sm text-text shadow-sm transition-colors hover:border-text/25 placeholder:text-text-dim focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
          />
          <select
            value={filterPlatform}
            onChange={(e) => setFilterPlatform(e.target.value)}
            className="w-40 rounded-lg border border-text/15 bg-bg-surface px-3 py-1.5 text-sm text-text shadow-sm transition-colors hover:border-text/25 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
          >
            {PLATFORM_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-bg-surface text-text">
                {o.translate ? tr(o.label) : o.label}
              </option>
            ))}
          </select>
        </div>

        {/* 空状态 */}
        {records.length === 0 && (
          <div className="mt-20 text-center text-sm text-text-muted">
            {tr("history_empty")}
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
            {tr("history_confirm_clear")}
          </p>
          <p className="mt-1 text-xs text-text-muted">
            注意：仅删除历史记录，不会删除已下载的文件。
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setConfirmClearOpen(false)}
              className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              {tr("cancel")}
            </button>
            <button
              onClick={onClear}
              className="rounded-lg bg-danger px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger-glow"
            >
              {tr("history_clear")}
            </button>
          </div>
        </ModalDialog>
      )}

      {/* 文件缺失对话框 */}
      {fileMissing && (
        <ModalDialog
          title={tr("file_missing_title")}
          onClose={() => setFileMissing(null)}
        >
          <p className="text-sm text-text">
            {tr("file_missing_msg")}
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
              {tr("cancel")}
            </button>
            <button
              onClick={onConfirmFileMissingDelete}
              disabled={!fileMissing.recordId}
              className="rounded-lg bg-danger px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger-glow disabled:opacity-40"
            >
              {tr("file_missing_delete")}
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
  const { tr } = useI18n();
  const hasThumb = !!record.thumbnail_url && record.thumbnail_url.length > 0;
  const hasFile = !!record.file_path && record.file_path.length > 0;

  return (
    <div className="library-card flex items-center gap-3.5 p-3.5">
      {/* Thumbnail / platform icon */}
      <div className="relative h-[62px] w-[62px] shrink-0 overflow-hidden rounded-xl border border-white/10 bg-black/30">
        {hasThumb ? (
          <img
            src={thumbProxyUrl(record.thumbnail_url, 200, 200, true)}
            alt=""
            className="h-full w-full object-cover"
            onError={(e) => {
              const img = e.currentTarget as HTMLImageElement;
              img.onerror = null;
              img.src = "";
              img.style.display = "none";
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
          {platformLabel(record.platform, tr)}
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
        {record.success ? tr("status_completed") : tr("status_failed")}
      </div>

      {/* Actions */}
      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={() => onOpenFile(record.file_path)}
          disabled={!hasFile}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
          title={tr("history_open_file")}
        >
          ▶
        </button>
        <button
          onClick={() => onOpenFolder(record.file_path)}
          disabled={!hasFile}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
          title={tr("history_open_dir")}
        >
          📂
        </button>
        <button
          onClick={() => onDelete(record.id)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-danger/10 hover:text-danger"
          title={tr("history_delete")}
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
