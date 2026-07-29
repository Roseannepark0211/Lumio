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
    合并中: "merging",
    解析中: "parsing",
  };
  return m[s] || s;
}

/** 状态对应的 pill 样式类（用于 Badge）。 */
export function statusPillClass(s: string): string {
  const n = normStatus(s);
  if (n === "completed") return "pill-success";
  if (n === "downloading" || n === "retrying") return "pill-accent";
  if (n === "failed" || n === "cancelled") return "pill-danger";
  if (n === "paused" || n === "interrupted") return "pill bg-warning/15 text-warning border border-warning/30";
  if (n === "merging" || n === "parsing") return "pill bg-accent/15 text-accent border border-accent/30";
  return "pill bg-white/5 text-text-muted";
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
