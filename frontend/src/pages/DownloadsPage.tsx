/**
 * React DownloadsPage — 复刻 QML DownloadsPage.qml 完整功能。
 *
 * 功能清单（与 QML 版本对齐）：
 *   1. 任务列表（拉取 + 状态过滤）
 *   2. 全局操作（全部开始/暂停/恢复）
 *   3. 单任务操作（开始/暂停/继续/重试/取消/删除）
 *   4. WebSocket 事件驱动刷新（queue_changed/task_status_changed/task_progress）
 *   5. 空状态提示
 *   6. 错误信息列表
 *
 * 与 QML 版本差异：
 *   - 暂未实现状态过滤 UI（QML 端也只定义了 filterStatus 属性但未暴露控件）
 *   - task_progress 事件局部更新（对应 QML 的 setProperty 优化，避免整列重渲染）
 */

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  api,
  subscribeEvents,
  type AppEvent,
  type QueueTask,
} from "../api";
import { useI18n } from "../i18n";
import { TaskCard } from "./downloads/TaskCard";
import {
  applyFilter,
  countActive,
  normStatus,
  type FilterStatus,
} from "../utils/downloads";

export function DownloadsPage() {
  const { tr } = useI18n();
  // —— 任务列表状态 ——
  const [tasks, setTasks] = useState<QueueTask[]>([]);
  const [filterStatus] = useState<FilterStatus>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 用于在 useEffect 中引用最新 tasks，避免闭包陈旧
  const tasksRef = useRef<QueueTask[]>([]);
  tasksRef.current = tasks;

  // —— 拉取队列 ——
  // 注意：对 downloading/retrying 状态的任务，保留前端最新的 progress/speed，
  // 不以后端返回的为准。因为 getQueue 返回的 progress 可能比 task_progress
  // 事件延迟（后端 getQueue 读取的是 qt.progress，而 task_progress 事件携带的
  // 是 downloader 实时上报的进度），全量覆盖会导致"进度条来回跳"。
  const reloadQueue = useCallback(async () => {
    try {
      const q = await api.getQueue();
      setTasks((prev) => {
        // 旧任务 progress 缓存（仅对活跃任务保留）
        const prevActive: Record<string, { progress: number; speed: string }> = {};
        for (const t of prev) {
          const n = normStatus(t.status);
          if (n === "downloading" || n === "retrying") {
            prevActive[t.task_id] = { progress: t.progress, speed: t.speed };
          }
        }
        // 合并：活跃任务保留前端 progress/speed，其他字段以后端为准
        return q.map((t) => {
          const cached = prevActive[t.task_id];
          const n = normStatus(t.status);
          if (cached && (n === "downloading" || n === "retrying")) {
            return { ...t, progress: cached.progress, speed: cached.speed };
          }
          return t;
        });
      });
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // —— 初次加载 ——
  useEffect(() => {
    reloadQueue();
  }, [reloadQueue]);

  // —— WebSocket 事件订阅 ——
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      switch (e.type) {
        // 全量刷新：队列整体变化（start_all / pause_all / cancel_all / cleanup 等）
        case "queue_changed":
          reloadQueue();
          break;

        // 增量 append：新任务加入队列
        case "task_added": {
          const newTask = e.data as QueueTask | null;
          if (newTask && newTask.task_id) {
            setTasks((prev) => {
              if (prev.some((t) => t.task_id === newTask.task_id)) return prev;
              return [...prev, newTask];
            });
          } else {
            reloadQueue();
          }
          break;
        }

        // 增量 patch：任务状态变更（暂停/继续/重试/恢复/中断）
        case "task_status_changed": {
          const p = e.data as { task_id?: string; status?: string } | null;
          if (!p?.task_id || !p.status) {
            reloadQueue();
            break;
          }
          const tid = p.task_id;
          const newStatus = p.status;
          setTasks((prev) =>
            prev.map((t) =>
              t.task_id === tid ? { ...t, status: newStatus } : t
            )
          );
          break;
        }

        // 增量 patch：任务完成（带 success/error）
        // 注意：task_status_changed 事件已携带正确中文 status（"已完成"/"失败"），
        // 这里不覆盖 status，只更新 progress/error，避免 status 被改成 "done" 导致 UI 不识别
        case "task_finished": {
          const p = e.data as
            | { task_id?: string; success?: boolean; error?: string }
            | null;
          if (!p?.task_id) {
            reloadQueue();
            break;
          }
          const tid = p.task_id;
          const success = !!p.success;
          const err = p.error || "";
          setTasks((prev) =>
            prev.map((t) =>
              t.task_id === tid
                ? {
                    ...t,
                    progress: success ? 1 : t.progress,
                    error: err,
                  }
                : t
            )
          );
          break;
        }

        // 局部更新事件（避免整列重渲染，对应 QML 的 setProperty 优化）
        case "task_progress": {
          const p = e.data as
            | { task_id?: string; progress?: number; speed?: string; filename?: string }
            | null;
          if (!p?.task_id) break;
          const tid = p.task_id;
          const newProgress = Math.max(0, Math.min(1, p.progress || 0));
          const newSpeed = p.speed || "";
          const newFilename = p.filename || "";
          // 用函数式更新确保拿到最新 tasks
          setTasks((prev) =>
            prev.map((t) =>
              t.task_id === tid
                ? {
                    ...t,
                    progress: newProgress,
                    speed: newSpeed || t.speed,
                    filename: newFilename || t.filename,
                  }
                : t
            )
          );
          break;
        }

        // 其他事件不处理
        default:
          break;
      }
    });
    return unsub;
  }, [reloadQueue]);

  // —— 单任务操作 ——
  const onStart = useCallback(async (id: string) => {
    console.log("[DownloadsPage] startTask:", id);
    try {
      await api.startTask(id);
    } catch (e) {
      console.warn("start task failed:", e);
    }
  }, []);
  const onPause = useCallback(async (id: string) => {
    console.log("[DownloadsPage] pauseTask:", id);
    try {
      await api.pauseTask(id);
    } catch (e) {
      console.warn("pause task failed:", e);
    }
  }, []);
  const onResume = useCallback(async (id: string) => {
    console.log("[DownloadsPage] resumeTask:", id);
    try {
      await api.resumeTask(id);
    } catch (e) {
      console.warn("resume task failed:", e);
    }
  }, []);
  const onRetry = useCallback(async (id: string) => {
    console.log("[DownloadsPage] retryTask:", id);
    try {
      await api.retryTask(id);
    } catch (e) {
      console.warn("retry task failed:", e);
    }
  }, []);
  const onCancel = useCallback(async (id: string) => {
    console.log("[DownloadsPage] cancelTask:", id);
    try {
      await api.cancelTask(id);
    } catch (e) {
      console.warn("cancel task failed:", e);
    }
  }, []);
  const onDelete = useCallback(async (id: string) => {
    console.log("[DownloadsPage] deleteTask:", id);
    try {
      await api.deleteTask(id);
    } catch (e) {
      console.warn("delete task failed:", e);
    }
  }, []);

  // —— 全局操作 ——
  const onStartAll = useCallback(async () => {
    console.log("[DownloadsPage] startAll (global)");
    try {
      await api.startAll();
    } catch (e) {
      console.warn("start all failed:", e);
    }
  }, []);
  const onPauseAll = useCallback(async () => {
    console.log("[DownloadsPage] pauseAll (global)");
    try {
      await api.pauseAll();
    } catch (e) {
      console.warn("pause all failed:", e);
    }
  }, []);
  const onResumeAll = useCallback(async () => {
    console.log("[DownloadsPage] resumeAll (global)");
    try {
      await api.resumeAll();
    } catch (e) {
      console.warn("resume all failed:", e);
    }
  }, []);

  // —— 派生状态 ——
  const filteredTasks = useMemo(
    () => applyFilter(tasks, filterStatus),
    [tasks, filterStatus]
  );
  const activeCount = useMemo(() => countActive(tasks), [tasks]);
  const errorTasks = useMemo(
    () => tasks.filter((t) => t.error && t.error.length > 0),
    [tasks]
  );

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
            <h1 className="text-xl font-bold text-text">{tr("queue_title")}</h1>
            <p className="mt-0.5 text-xs text-text-muted">
              {tr("downloads_subtitle")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* 活跃任务数 pill */}
            <div className="rounded-full border border-accent/30 bg-accent/15 px-2.5 py-1 text-xs font-semibold text-accent">
              {activeCount} {tr("active")}
            </div>
            {/* 全局操作按钮 */}
            <button
              onClick={onStartAll}
              className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-glow"
              title={tr("start_all")}
            >
              ▶ {tr("start_all")}
            </button>
            <button
              onClick={onPauseAll}
              className="flex items-center gap-1.5 rounded-lg bg-white/5 px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
              title={tr("pause_all")}
            >
              ⏸ {tr("pause_all")}
            </button>
            <button
              onClick={onResumeAll}
              className="flex items-center gap-1.5 rounded-lg bg-white/5 px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
              title={tr("resume_interrupted")}
            >
              ↻ {tr("resume_interrupted")}
            </button>
          </div>
        </header>

        {/* 空状态 */}
        {tasks.length === 0 && (
          <div className="mt-20 text-center text-sm text-text-muted">
            {tr("downloads_empty")}
          </div>
        )}

        {/* 任务列表 */}
        {tasks.length > 0 && (
          <div className="flex flex-col gap-2">
            {filteredTasks.map((t) => (
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

        {/* 错误信息列表 */}
        {errorTasks.length > 0 && (
          <div className="mt-2 flex flex-col gap-1">
            {errorTasks.map((t) => (
              <div
                key={t.task_id}
                className="rounded-lg border border-danger/20 bg-danger/5 px-3 py-1.5 text-xs text-danger"
              >
                ⚠ {t.title || t.url}: {t.error}
              </div>
            ))}
          </div>
        )}

        {/* 底部 spacer */}
        <div className="h-12" />
      </div>
    </div>
  );
}
