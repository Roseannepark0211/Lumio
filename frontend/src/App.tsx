import React, { useEffect, useState, useCallback, useRef } from "react";
import { subscribeEvents, type AppEvent } from "./api";
import { getPageSwitch } from "./config";
import { Sidebar, type PageKey } from "./Sidebar";
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
 * 双窗口架构（main.ts 保证主窗口 show 时 FastAPI 已 ready）：
 *   1. Electron main.ts 创建 splash 窗口立即显示 loading
 *   2. main.ts 创建主窗口（show: false）后台加载 React
 *   3. React 渲染完毕（ready-to-show）+ FastAPI ready → 主窗口 show + splash 销毁
 *   4. App 挂载时 FastAPI 已 ready，直接渲染主 UI
 *
 * App 内不再做 bootState 轮询，避免与 main.ts 双重轮询冲突。
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

  // —— 全局页面导航（通知页 action 按钮 "open_page:settings" 用 + 托盘菜单导航） ——
  const [currentPage, setCurrentPage] = useState<PageKey | null>(null);
  const navigate = useCallback((page: string) => {
    const valid: PageKey[] = ["home", "downloads", "history", "library", "inbox", "stats", "notifications", "settings"];
    if (valid.includes(page as PageKey)) {
      setCurrentPage(page as PageKey);
    }
  }, []);

  // 监听 Electron 托盘菜单导航事件（window.lumio.onNavigate 由 preload 暴露）
  useEffect(() => {
    const lumioGlobal = (window as unknown as { lumio?: { onNavigate?: (cb: (page: string) => void) => void } }).lumio;
    if (lumioGlobal?.onNavigate) {
      lumioGlobal.onNavigate((page: string) => navigate(page));
    }
  }, [navigate]);

  // 没有任何 React 页面启用 → 显示简洁兜底（正式版所有页面已启用，此分支理论上不触发）
  if (enabledPages.length === 0) {
    return (
      <div className="flex h-screen items-center justify-center text-text-muted">
        No pages enabled. Check frontend/config.ts.
      </div>
    );
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
            <div className="glass-card max-w-md rounded-xl px-4 py-2.5 text-sm text-text">
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
 * POC 验证页面 + StatusPill/formatSize 工具函数已删除
 * （正式版所有页面已启用，脚手架兜底不再需要）。
 * 历史版本：commit 之前的 git log 可查 PocPage 实现。
 */
