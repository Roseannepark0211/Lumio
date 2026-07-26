/**
 * Downloads 页面工具函数 — 复刻 QML DownloadsPage.qml 内的辅助函数。
 *
 * 对应 QML 函数：
 *   - _normStatus / _statusText / _statusColor
 *   - _formatSize / _formatPct
 *   - _applyFilter / _activeCount
 */

import type { QueueTask } from "../api";

/** 后端状态归一化：把中文/英文状态值统一映射为英文 key。 */
export function normStatus(s: string): string {
  const m: Record<string, string> = {
    等待中: "waiting",
    下载中: "downloading",
    暂停中: "paused",
    重试中: "retrying",
    已中断: "interrupted",
    已完成: "completed",
    失败: "failed",
    已取消: "cancelled",
  };
  return m[s] || s;
}

/** 状态显示文本（i18n 在后端已完成，前端直接做中文映射）。 */
export function statusText(s: string): string {
  const n = normStatus(s);
  const m: Record<string, string> = {
    waiting: "等待中",
    downloading: "下载中",
    paused: "暂停中",
    retrying: "重试中",
    interrupted: "已中断",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  return m[n] || s;
}

/** 状态对应的 Tailwind 文本颜色类。 */
export function statusColorClass(s: string): string {
  const n = normStatus(s);
  if (n === "completed") return "text-success";
  if (n === "downloading") return "text-accent";
  if (n === "failed" || n === "cancelled") return "text-danger";
  if (n === "paused" || n === "interrupted") return "text-warning";
  return "text-text-muted";
}

/** 状态对应的 pill 样式类（用于 Badge）。 */
export function statusPillClass(s: string): string {
  const n = normStatus(s);
  if (n === "completed") return "pill-success";
  if (n === "downloading" || n === "retrying") return "pill-accent";
  if (n === "failed" || n === "cancelled") return "pill-danger";
  if (n === "paused" || n === "interrupted") return "pill bg-warning/15 text-warning border border-warning/30";
  return "pill bg-white/5 text-text-muted";
}

/** 字节格式化：B / KB / MB / GB。 */
export function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/** 0..1 → "NN%"。 */
export function formatPct(p: number): string {
  return `${Math.round((p || 0) * 100)}%`;
}

export type FilterStatus = "all" | "downloading" | "paused" | "completed" | "failed";

/** 按 filterStatus 过滤任务列表。 */
export function applyFilter(tasks: QueueTask[], filter: FilterStatus): QueueTask[] {
  if (filter === "all") return tasks;
  return tasks.filter((t) => {
    const s = normStatus(t.status);
    if (filter === "downloading") return s === "downloading" || s === "retrying";
    if (filter === "paused") return s === "paused" || s === "interrupted";
    if (filter === "completed") return s === "completed";
    if (filter === "failed") return s === "failed" || s === "cancelled";
    return true;
  });
}

/** 统计活跃任务数（downloading + retrying）。 */
export function countActive(tasks: QueueTask[]): number {
  return tasks.filter((t) => {
    const n = normStatus(t.status);
    return n === "downloading" || n === "retrying";
  }).length;
}
