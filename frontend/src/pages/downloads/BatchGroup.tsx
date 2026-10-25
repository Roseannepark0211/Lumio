/**
 * BatchGroup — 批量下载分组（重构阶段 3）。
 *
 * 队列里同一 batch_id 的任务折叠成一组：组头显示文件夹名 + x/N 进度
 * （来自 GET /api/batch/{batch_id} 的汇总，已完成任务 1.5 秒后自动从
 * 队列移除，进度靠后端“队列 + 历史记录”拼出，前端只做展示）；
 * 展开后复用 TaskCard 渲染单项（开始/暂停/重试/取消/删除均复用已有逻辑，
 * 单项失败不影响其他项，失败项用 TaskCard 自带的重试按钮单独重试）。
 * 整批完成后组头下方显示汇总（成功 x 个、失败名单），任务全部消失后
 * 该组以“已完成行”保留在页内，直到用户点 ✕ 关闭（刷新后不再出现，
 * 因为后端 registry 是进程内的）。
 */

import { useState } from "react";
import type { QueueTask, BatchSummary } from "../../api";
import { useI18n } from "../../i18n";
import { TaskCard } from "./TaskCard";

interface BatchGroupProps {
  batchId: string;
  tasks: QueueTask[];
  summary: BatchSummary | null;
  onStart: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onRetry: (id: string) => void;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
  onDismissCompleted: (batchId: string) => void;
}

function baseNameOf(outputDir: string): string {
  if (!outputDir) return "";
  const parts = outputDir.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || outputDir;
}

export function BatchGroup({
  batchId,
  tasks,
  summary,
  onStart,
  onPause,
  onResume,
  onRetry,
  onCancel,
  onDelete,
  onDismissCompleted,
}: BatchGroupProps) {
  const { tr } = useI18n();
  // 进行中的组默认展开，已完成的组默认折叠（只看汇总）
  const [expanded, setExpanded] = useState(summary?.status !== "done");
  const isDone = summary?.status === "done";
  const folderName =
    summary?.folder_name || baseNameOf(tasks[0]?.output_dir || "") || batchId;
  const failedTitles = (summary?.failed || [])
    .map((f) => f.title)
    .filter(Boolean)
    .slice(0, 3);

  return (
    <div className="glass-card overflow-hidden">
      {/* 组头：点击折叠/展开 */}
      <div
        className="flex cursor-pointer items-center gap-2 px-4 py-3"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="text-base">📁</span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-text">
          {folderName}
        </span>
        {summary ? (
          <span className="shrink-0 text-xs text-text-muted">
            {tr("batch_progress", { done: summary.done, total: summary.total })}
          </span>
        ) : (
          <span className="shrink-0 text-xs text-text-muted">
            {tasks.length} 项
          </span>
        )}
        {summary && summary.failed_count > 0 && (
          <span className="shrink-0 rounded-full bg-danger/15 px-2 py-0.5 text-xs font-semibold text-danger">
            失败 {summary.failed_count}
          </span>
        )}
        <span className="shrink-0 text-xs text-text-muted">
          {expanded ? "▴" : "▾"}
        </span>
        {/* 已完成且队列里已无任务时，允许关闭该已完成行 */}
        {isDone && tasks.length === 0 && (
          <button
            type="button"
            aria-label="关闭"
            onClick={(e) => {
              e.stopPropagation();
              onDismissCompleted(batchId);
            }}
            className="shrink-0 rounded-lg px-2 py-1 text-sm leading-none text-text-muted hover:bg-bg-elevated hover:text-text"
          >
            ×
          </button>
        )}
      </div>

      {/* 整批完成汇总 */}
      {isDone && summary && (
        <div className="border-t px-4 py-2 text-xs text-text-muted">
          {tr("batch_done_summary", {
            done: summary.done,
            failed: summary.failed_count,
          })}
          {failedTitles.length > 0 && (
            <span>
              {" "}
              {tr("batch_failed_titles", { titles: failedTitles.join("、") })}
              {summary.failed_count > failedTitles.length ? "等" : ""}
            </span>
          )}
        </div>
      )}

      {/* 组内任务：复用 TaskCard */}
      {expanded && tasks.length > 0 && (
        <div className="flex flex-col gap-2 border-t p-2">
          {tasks.map((t) => (
            <TaskCard
              key={t.task_id}
              task={t}
              onStart={onStart}
              onPause={onPause}
              onResume={onResume}
              onRetry={onRetry}
              onCancel={onCancel}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
