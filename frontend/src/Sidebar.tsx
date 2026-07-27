import { useEffect, useState, useCallback } from "react";
import { api, subscribeEvents, type AppEvent } from "./api";

/**
 * 左侧固定导航栏 — AGENTS.md 规定：
 *   "Sidebar 导航：左侧固定导航栏，8 个页面
 *    （Home/Inbox/Downloads/History/Library/Stats/Notifications/Settings），
 *    含红点徽章（1-9 圆点 / 10-99 胶囊 / ≥100 显示 99+）"
 *
 * 徽章来源：
 *   - Inbox: 未读收件箱条目数 (/api/inbox/unread-count)
 *   - Downloads: 活跃下载数（downloading + queued + retrying）
 *   - Notifications: 未读通知数 (/api/notifications/unread-count)
 *
 * 主题切换按钮放底部（AGENTS.md "Light/Dark 主题：侧边栏底部切换按钮"）
 */

export type PageKey =
  | "home"
  | "inbox"
  | "downloads"
  | "history"
  | "library"
  | "stats"
  | "notifications"
  | "settings";

interface SidebarProps {
  current: PageKey;
  onNavigate: (page: PageKey) => void;
  enabledPages: PageKey[];
}

/** 单个导航项配置：图标 + 文案 + 徽章来源 */
interface NavItem {
  key: PageKey;
  label: string;
  icon: React.ReactNode;
  badge?: number; // 0 / undefined = 不显示
}

export function Sidebar({ current, onNavigate, enabledPages }: SidebarProps) {
  // —— 徽章计数 ——
  const [inboxCount, setInboxCount] = useState(0);
  const [notifCount, setNotifCount] = useState(0);
  const [activeDownloads, setActiveDownloads] = useState(0);

  const refreshInbox = useCallback(async () => {
    try {
      const r = await api.getInboxUnreadCount();
      setInboxCount(r.count || 0);
    } catch {
      /* ignore */
    }
  }, []);

  const refreshNotifs = useCallback(async () => {
    try {
      const r = await api.getUnreadCount();
      setNotifCount(r.count || 0);
    } catch {
      /* ignore */
    }
  }, []);

  const refreshDownloads = useCallback(async () => {
    try {
      const q = await api.getQueue();
      const active = q.filter((t) =>
        ["downloading", "queued", "retrying", "paused"].includes(t.status)
      ).length;
      setActiveDownloads(active);
    } catch {
      /* ignore */
    }
  }, []);

  // 首次加载拉一次
  useEffect(() => {
    refreshInbox();
    refreshNotifs();
    refreshDownloads();
  }, [refreshInbox, refreshNotifs, refreshDownloads]);

  // 监听 WS 事件刷新徽章
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      switch (e.type) {
        case "inbox_changed":
          refreshInbox();
          break;
        case "notification_changed":
          refreshNotifs();
          break;
        case "queue_changed":
        case "task_added":
        case "task_started":
        case "task_finished":
        case "task_status_changed":
          refreshDownloads();
          break;
      }
    });
    return unsub;
  }, [refreshInbox, refreshNotifs, refreshDownloads]);

  // —— 导航项列表（按 AGENTS.md 规定顺序） ——
  const navItems: NavItem[] = [
    {
      key: "home",
      label: "Home",
      icon: <HomeIcon />,
    },
    {
      key: "inbox",
      label: "Inbox",
      icon: <InboxIcon />,
      badge: inboxCount,
    },
    {
      key: "downloads",
      label: "Downloads",
      icon: <DownloadIcon />,
      badge: activeDownloads,
    },
    {
      key: "history",
      label: "History",
      icon: <HistoryIcon />,
    },
    {
      key: "library",
      label: "Library",
      icon: <LibraryIcon />,
    },
    {
      key: "stats",
      label: "Stats",
      icon: <StatsIcon />,
    },
    {
      key: "notifications",
      label: "Notifications",
      icon: <BellIcon />,
      badge: notifCount,
    },
    {
      key: "settings",
      label: "Settings",
      icon: <SettingsIcon />,
    },
  ];

  // 只显示已启用的页面
  const visibleItems = navItems.filter((item) => enabledPages.includes(item.key));

  return (
    <aside className="sidebar-glass flex h-full w-[200px] shrink-0 flex-col border-r border-white/5">
      {/* Logo / App 名称 */}
      <div className="flex h-14 shrink-0 items-center gap-2.5 px-5">
        <div className="h-7 w-7 shrink-0 rounded-lg bg-gradient-to-br from-accent to-accent-glow shadow-lg shadow-accent/30" />
        <span className="text-base font-bold tracking-tight text-text">Lumio</span>
      </div>

      {/* 导航项列表 */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
        {visibleItems.map((item) => {
          const isActive = current === item.key;
          return (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              className={`group relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                isActive
                  ? "bg-white/10 text-text"
                  : "text-text-muted hover:bg-white/5 hover:text-text"
              }`}
            >
              {/* 激活态左侧指示条 */}
              {isActive && (
                <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-accent" />
              )}
              <span className="shrink-0">{item.icon}</span>
              <span className="flex-1 text-left">{item.label}</span>
              {/* 徽章 */}
              {item.badge && item.badge > 0 && <Badge count={item.badge} />}
            </button>
          );
        })}
      </nav>

      {/* 底部：主题切换按钮（AGENTS.md 规定） */}
      <div className="shrink-0 border-t border-white/5 p-3">
        <ThemeToggle />
      </div>
    </aside>
  );
}

// ============================================================
// 徽章 — 1-9 圆点 / 10-99 胶囊 / ≥100 显示 99+
// ============================================================

function Badge({ count }: { count: number }) {
  if (count <= 0) return null;
  // 1-9: 小圆点
  if (count < 10) {
    return (
      <span className="inline-flex h-2 w-2 shrink-0 rounded-full bg-danger shadow-sm shadow-danger/50" />
    );
  }
  // 10-99: 胶囊显示数字
  if (count < 100) {
    return (
      <span className="inline-flex h-4 min-w-[16px] shrink-0 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white shadow-sm shadow-danger/50">
        {count}
      </span>
    );
  }
  // ≥100: 显示 99+
  return (
    <span className="inline-flex h-4 min-w-[20px] shrink-0 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white shadow-sm shadow-danger/50">
      99+
    </span>
  );
}

// ============================================================
// 主题切换按钮（占位实现 — 主题切换接入在第 3 步做）
// ============================================================

function ThemeToggle() {
  // TODO: 接入主题切换时实现完整逻辑
  // 当前是占位按钮，避免阻塞 Sidebar 迁移
  return (
    <button
      className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-text-muted transition-colors hover:bg-white/5 hover:text-text"
      title="主题切换（即将实现）"
    >
      <SunIcon />
      <span>Light / Dark</span>
    </button>
  );
}

// ============================================================
// 图标 — 简洁线性 SVG，与 Liquid Glass 风格协调
// ============================================================

const iconClass = "h-4 w-4 shrink-0";

function HomeIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 11l9-8 9 8M5 10v10a1 1 0 001 1h12a1 1 0 001-1V10" />
    </svg>
  );
}

function InboxIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function HistoryIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v5h5" />
      <path d="M3.05 13A9 9 0 106 5.3L3 8" />
      <path d="M12 7v5l4 2" />
    </svg>
  );
}

function LibraryIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
    </svg>
  );
}

function StatsIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 01-3.46 0" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}
