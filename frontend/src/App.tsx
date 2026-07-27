import React, { useEffect, useState, useCallback, useRef } from "react";
import { api, subscribeEvents, type AppEvent, type HealthResponse, type QueueTask, type LibraryItem } from "./api";
import { getPageSwitch } from "./config";
import { Sidebar, type PageKey } from "./Sidebar";
import { useI18n } from "./i18n";
import { HomePage } from "./pages/HomePage";
import { DownloadsPage } from "./pages/DownloadsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { LibraryPage } from "./pages/LibraryPage";
import { InboxPage } from "./pages/InboxPage";
import { StatsPage } from "./pages/StatsPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { SettingsPage } from "./pages/SettingsPage";

// 全局 Toast 上下文 — 任何页面都能触发 toast
const ToastContext = React.createContext<(msg: string) => void>(() => {});
export const useToast = () => React.useContext(ToastContext);

// 全局页面导航上下文 — 通知页 action 按钮 "open_page:settings" 用
const NavContext = React.createContext<(page: string) => void>(() => {});
export const useNav = () => React.useContext(NavContext);

/**
 * 应用根组件。
 *
 * 根据 config.ts 中的页面级开关决定加载哪些 React 页面：
 *   - 启用的页面会出现在顶部 tab 切换栏
 *   - 未启用的页面 fallback 到 QML 版本（由 Electron 主进程处理）
 *
 * 后续迁移其他页面时同样按开关切换。
 */
export default function App() {
  const useReactHome = getPageSwitch("USE_REACT_HOME");
  const useReactDownloads = getPageSwitch("USE_REACT_DOWNLOADS");
  const useReactHistory = getPageSwitch("USE_REACT_HISTORY");
  const useReactLibrary = getPageSwitch("USE_REACT_LIBRARY");
  const useReactInbox = getPageSwitch("USE_REACT_INBOX");
  const useReactStats = getPageSwitch("USE_REACT_STATS");
  const useReactNotifications = getPageSwitch("USE_REACT_NOTIFICATIONS");
  const useReactSettings = getPageSwitch("USE_REACT_SETTINGS");

  // 已启用的 React 页面列表
  const enabledPages: PageKey[] = [];
  if (useReactHome) enabledPages.push("home");
  if (useReactDownloads) enabledPages.push("downloads");
  if (useReactHistory) enabledPages.push("history");
  if (useReactLibrary) enabledPages.push("library");
  if (useReactInbox) enabledPages.push("inbox");
  if (useReactStats) enabledPages.push("stats");
  if (useReactNotifications) enabledPages.push("notifications");
  if (useReactSettings) enabledPages.push("settings");

  // —— 全局 Toast ——
  // 监听 WS `toast` 事件 + 暴露 triggerToast 给所有页面用
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);
  const triggerToast = useCallback((msg: string) => {
    if (!msg) return;
    setToastMsg(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastMsg(null), 2800);
  }, []);

  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      if (e.type === "toast") {
        const msg = (e.data as { message?: string })?.message || "";
        if (msg) triggerToast(msg);
      }
    });
    return unsub;
  }, [triggerToast]);

  // —— 全局页面导航（通知页 action 按钮 "open_page:settings" 用） ——
  const [currentPage, setCurrentPage] = useState<PageKey | null>(null);
  const navigate = useCallback((page: string) => {
    const valid: PageKey[] = ["home", "downloads", "history", "library", "inbox", "stats", "notifications", "settings"];
    if (valid.includes(page as PageKey)) {
      setCurrentPage(page as PageKey);
    }
  }, []);

  // 没有任何 React 页面启用 → 显示 POC 验证页
  if (enabledPages.length === 0) {
    return <PocPage />;
  }

  return (
    <ToastContext.Provider value={triggerToast}>
      <NavContext.Provider value={navigate}>
        <PageSwitcher
          pages={enabledPages}
          current={currentPage}
          setCurrent={setCurrentPage}
        />
        {/* 全局 Toast 渲染 — 固定在屏幕底部居中 */}
        {toastMsg && (
          <div className="pointer-events-none fixed bottom-8 left-1/2 z-[100] -translate-x-1/2 animate-slide-up">
            <div className="glass-card max-w-md rounded-xl border border-white/10 bg-zinc-900/95 px-4 py-2.5 text-sm text-text shadow-2xl">
              {toastMsg}
            </div>
          </div>
        )}
      </NavContext.Provider>
    </ToastContext.Provider>
  );
}

/** 左右布局：Sidebar + 页面内容区 */
function PageSwitcher({
  pages,
  current,
  setCurrent,
}: {
  pages: PageKey[];
  current: PageKey | null;
  setCurrent: (p: PageKey) => void;
}) {
  // current 为 null（首次）或不在 pages 列表中时，重置为第一个
  useEffect(() => {
    if (!current || (!pages.includes(current) && pages.length > 0)) {
      setCurrent(pages[0]);
    }
  }, [pages, current, setCurrent]);

  const effective = current && pages.includes(current) ? current : pages[0];

  return (
    <div className="flex h-full">
      {/* 左侧固定 Sidebar（AGENTS.md 规定 200px 宽） */}
      <Sidebar
        current={effective}
        onNavigate={setCurrent}
        enabledPages={pages}
      />

      {/* 右侧页面内容 — keep-alive 模式：所有页面同时挂载，用 display 切换
          避免切换页面时 unmount/remount 导致重新拉数据 + 图片重新加载 */}
      <div className="min-h-0 min-w-0 flex-1">
        <div style={{ display: effective === "home" ? "contents" : "none" }}>
          <HomePage />
        </div>
        <div style={{ display: effective === "downloads" ? "contents" : "none" }}>
          <DownloadsPage />
        </div>
        <div style={{ display: effective === "history" ? "contents" : "none" }}>
          <HistoryPage />
        </div>
        <div style={{ display: effective === "library" ? "contents" : "none" }}>
          <LibraryPage />
        </div>
        <div style={{ display: effective === "inbox" ? "contents" : "none" }}>
          <InboxPage />
        </div>
        <div style={{ display: effective === "stats" ? "contents" : "none" }}>
          <StatsPage />
        </div>
        <div style={{ display: effective === "notifications" ? "contents" : "none" }}>
          <NotificationsPage />
        </div>
        <div style={{ display: effective === "settings" ? "contents" : "none" }}>
          <SettingsPage />
        </div>
      </div>
    </div>
  );
}

/**
 * POC 验证页面：拉取 FastAPI 真实数据，验证 Electron 渲染进程 → FastAPI 链路。
 *
 * 这不是最终 UI，只是脚手架阶段的连通性验证。
 * 后续每个页面会按 design_preview/ 下的设计稿单独迁移。
 */
function PocPage() {
  const { tr } = useI18n();
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
        <div className="text-text-muted">{tr("loading")}</div>
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
          {tr("downloads")} ({queue.length})
        </h2>
        <div className="space-y-2">
          {queue.length === 0 ? (
            <div className="glass-card p-4 text-sm text-text-muted">{tr("downloads_empty")}</div>
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
          {tr("library")} ({library.length})
        </h2>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
          {library.slice(0, 12).map((it) => (
            <div key={it.id} className="glass-card p-3">
              <div className="truncate text-sm font-medium">{it.title || "(无标题)"}</div>
              <div className="mt-1 text-xs text-text-muted">
                {it.platform} · {formatSize(it.file_size)}
              </div>
              {it.is_favorite && (
                <span className="pill-danger mt-2">★ {tr("library_toggle_fav")}</span>
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
