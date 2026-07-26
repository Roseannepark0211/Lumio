import { useEffect, useState } from "react";
import { api, type HealthResponse, type QueueTask, type LibraryItem } from "./api";

/**
 * POC 验证页面：拉取 FastAPI 真实数据，验证 Electron 渲染进程 → FastAPI 链路。
 *
 * 这不是最终 UI，只是脚手架阶段的连通性验证。
 * 后续每个页面会按 design_preview/ 下的设计稿单独迁移。
 */
export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [queue, setQueue] = useState<QueueTask[]>([]);
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [h, q, l] = await Promise.all([
          api.getHealth(),
          api.getQueue(),
          api.getLibrary(),
        ]);
        setHealth(h);
        setQueue(q);
        setLibrary(l);
      } catch (e) {
        setError(String(e));
      }
    })();
  }, []);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="glass-card max-w-md p-6">
          <h2 className="text-lg font-semibold text-danger">连接失败</h2>
          <p className="mt-2 text-sm text-text-muted">{error}</p>
          <p className="mt-4 text-xs text-text-muted">
            请确认 FastAPI 服务已启动：<code className="font-mono">python -m lumio.api_fastapi</code>
          </p>
        </div>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-text-muted">加载中...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-8">
      <header className="mb-8 animate-fade-in">
        <h1 className="text-3xl font-bold tracking-tight">
          Lumio <span className="text-accent">Electron POC</span>
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          FastAPI 链路验证 · 后端版本 v{health.version}
        </p>
      </header>

      {/* Health 卡片 */}
      <section className="mb-8 animate-slide-up">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
          后端状态
        </h2>
        <div className="glass-card p-5">
          <div className="flex items-center gap-3">
            <div className="h-2 w-2 animate-pulse rounded-full bg-success" />
            <span className="text-sm font-medium">服务正常</span>
          </div>
          <div className="mt-4 grid grid-cols-5 gap-3 text-xs">
            {Object.entries(health.managers).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <div
                  className={`h-1.5 w-1.5 rounded-full ${
                    v ? "bg-success" : "bg-danger"
                  }`}
                />
                <span className="text-text-muted">{k}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 队列 */}
      <section className="mb-8 animate-slide-up">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
          下载队列 ({queue.length})
        </h2>
        <div className="space-y-2">
          {queue.length === 0 ? (
            <div className="glass-card p-4 text-sm text-text-muted">队列为空</div>
          ) : (
            queue.map((t) => (
              <div key={t.task_id} className="glass-card p-4">
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{t.title || t.url}</div>
                    <div className="mt-0.5 text-xs text-text-muted">
                      {t.platform} · {t.author || "unknown"}
                    </div>
                  </div>
                  <StatusPill status={t.status} />
                </div>
                {t.progress > 0 && t.status === "downloading" && (
                  <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/5">
                    <div
                      className="h-full bg-accent transition-all"
                      style={{ width: `${t.progress * 100}%` }}
                    />
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      {/* 素材库 */}
      <section className="mb-8 animate-slide-up">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
          素材库 ({library.length})
        </h2>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
          {library.slice(0, 12).map((it) => (
            <div key={it.id} className="glass-card p-3">
              <div className="truncate text-sm font-medium">{it.title || "(无标题)"}</div>
              <div className="mt-1 text-xs text-text-muted">
                {it.platform} · {formatSize(it.file_size)}
              </div>
              {it.is_favorite && (
                <span className="pill-danger mt-2">★ 收藏</span>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === "done"
      ? "pill-success"
      : status === "downloading"
      ? "pill-accent"
      : status === "failed"
      ? "pill-danger"
      : "pill bg-white/5 text-text-muted";
  const label =
    status === "done"
      ? "完成"
      : status === "downloading"
      ? "下载中"
      : status === "failed"
      ? "失败"
      : status === "paused"
      ? "已暂停"
      : status === "queued"
      ? "排队中"
      : status;
  return <span className={cls}>{label}</span>;
}

function formatSize(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}
