/**
 * TaskCard — 下载任务卡片（复刻 QML DownloadsPage.qml 内的 GlassCard delegate）。
 *
 * 字段映射（QueueTask → UI）：
 *   - thumbnail_url → 缩略图（无则显示 audio/video 占位图标）
 *   - title / url   → 标题（优先 title，兜底 url）
 *   - author · platform · speed → 元信息行
 *   - progress      → LaserProgressBar（compact 模式）
 *   - status        → Badge + 按钮状态切换
 *   - error         → 由父组件统一渲染错误列表
 *
 * 按钮交互（与 QML 对齐）：
 *   - 开始/暂停/继续：downloading→pause，paused/interrupted→resume，其他→start
 *   - 重试：仅 failed/cancelled 可见
 *   - 取消：downloading/paused/waiting/retrying 可用
 *   - 删除：始终可用
 */

import { memo } from "react";
import type { QueueTask } from "../../api";
import { thumbProxyUrl } from "../../api";
import { LaserProgressBar } from "../../components/LaserProgressBar";
import {
  normStatus,
  statusText,
  statusPillClass,
  formatPct,
} from "../../utils/downloads";

interface TaskCardProps {
  task: QueueTask;
  onStart: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onRetry: (id: string) => void;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
}

function TaskCardImpl({
  task,
  onStart,
  onPause,
  onResume,
  onRetry,
  onCancel,
  onDelete,
}: TaskCardProps) {
  const n = normStatus(task.status);
  const hasThumb = !!task.thumbnail_url && task.thumbnail_url.length > 0;
  // QML 用 format_type 判断 audio/video 占位图标，但 _task_to_dict 未返回此字段
  // 改用 media_type 字段判断（更准确）
  const isAudio = task.media_type === "audio";
  const isActive = n === "downloading" || n === "retrying";

  // 开始/暂停/继续按钮的图标和点击行为
  const toggleIcon =
    n === "downloading" ? "⏸" : n === "paused" || n === "interrupted" ? "▶" : "▶";
  const toggleEnabled =
    n === "waiting" || n === "paused" || n === "interrupted" || n === "downloading";
  const onToggleClick = () => {
    if (n === "downloading") onPause(task.task_id);
    else if (n === "paused" || n === "interrupted") onResume(task.task_id);
    else onStart(task.task_id);
  };

  // 重试按钮可见性
  const retryVisible = n === "failed" || n === "cancelled";

  // 取消按钮可用性
  const cancelEnabled =
    n === "downloading" || n === "paused" || n === "waiting" || n === "retrying";

  return (
    <div className="glass-card flex items-center gap-3.5 p-3.5">
      {/* Thumbnail */}
      <div className="relative h-[62px] w-[62px] shrink-0 overflow-hidden rounded-xl border border-white/10 bg-black/30">
        {hasThumb ? (
          <img
            src={thumbProxyUrl(task.thumbnail_url)}
            alt=""
            className="h-full w-full object-cover"
            onError={(e) => {
              // 加载失败隐藏 img，显示占位图标
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-white/60">
            <span className="text-lg">{isAudio ? "🎵" : "🎬"}</span>
          </div>
        )}
      </div>

      {/* Info 列 */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {/* 标题 */}
        <div className="truncate text-sm font-semibold text-text">
          {task.title || task.url}
        </div>
        {/* 元信息 */}
        <div className="truncate text-xs text-text-muted">
          {task.author || ""}
          {task.author && task.platform ? " · " : ""}
          {(task.platform || "").toUpperCase()}
          {task.speed ? " · " : ""}
          {task.speed || ""}
        </div>
        {/* 激光进度条（compact 模式） */}
        <LaserProgressBar
          progress={task.progress}
          compact
          particlesEnabled={isActive}
        />
      </div>

      {/* 进度百分比 */}
      <div className="shrink-0 font-mono text-xs font-semibold text-text-muted">
        {formatPct(task.progress)}
      </div>

      {/* 状态 Badge */}
      <div className={`shrink-0 ${statusPillClass(task.status)}`}>
        {statusText(task.status)}
      </div>

      {/* 操作按钮组 */}
      <div className="flex shrink-0 items-center gap-1">
        {/* 开始/暂停/继续 */}
        <button
          onClick={onToggleClick}
          disabled={!toggleEnabled}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
          title={n === "downloading" ? "暂停" : "开始/继续"}
        >
          {toggleIcon}
        </button>

        {/* 重试（仅失败时） */}
        {retryVisible && (
          <button
            onClick={() => onRetry(task.task_id)}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            title="重试"
          >
            ↻
          </button>
        )}

        {/* 取消 */}
        <button
          onClick={() => onCancel(task.task_id)}
          disabled={!cancelEnabled}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
          title="取消"
        >
          ✕
        </button>

        {/* 删除 */}
        <button
          onClick={() => onDelete(task.task_id)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-danger/10 hover:text-danger"
          title="删除"
        >
          🗑
        </button>
      </div>
    </div>
  );
}

export const TaskCard = memo(TaskCardImpl);
