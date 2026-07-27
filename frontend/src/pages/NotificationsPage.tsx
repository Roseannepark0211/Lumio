/**
 * React NotificationsPage — 复刻 QML NotificationsPage.qml 完整功能。
 *
 * 功能清单（与 QML 版本对齐）：
 *   1. 未读 badge（顶部统计：未读数 · 总数）
 *   2. 全部已读 / 清除已读（永久通知保留）
 *   3. 分类筛选（all/deps/env/update/system/permanent）
 *   4. 优先级视觉（critical 红色左边条 / high 橙色 / normal 默认 / low 半透明）
 *   5. 永久通知锁图标（不可关闭）
 *   6. 整卡点击标记已读
 *   7. Action 按钮（open_page / open_url）
 *   8. WebSocket 事件 notification_changed 驱动刷新
 *
 * 与 QML 版本差异：
 *   - QML 用 Qt.callLater 解决 click → reload → delegate 销毁的崩溃
 *     React 用 functional setState 自动 batch，无需延迟
 *   - QML 用 MouseArea propagateComposedEvents 透传按钮点击
 *     React 用 stopPropagation 在按钮 onClick 上阻止冒泡
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import {
  api,
  subscribeEvents,
  type AppEvent,
  type NotificationItem,
} from "../api";
import { useNav } from "../App";
import { useI18n } from "../i18n";

// ============================================================
// 常量
// ============================================================

// 分类筛选选项（与 QML NotificationsPage.qml model 对齐）
// labelKey 字段为 i18n key，在渲染时通过 tr() 解析
const FILTER_OPTIONS: {
  value: string;
  labelKey: string;
  color: string; // tailwind text-* 类
  bg: string;    // tailwind bg-*/10 类
  border: string;
}[] = [
  { value: "all",        labelKey: "notif_filter_all",    color: "text-accent",      bg: "bg-accent/15",      border: "border-accent/40" },
  { value: "deps",       labelKey: "notif_cat_deps",      color: "text-warning",     bg: "bg-warning/15",     border: "border-warning/40" },
  { value: "env",        labelKey: "notif_cat_env",       color: "text-info",        bg: "bg-info/15",        border: "border-info/40" },
  { value: "update",     labelKey: "notif_cat_update",    color: "text-success",     bg: "bg-success/15",     border: "border-success/40" },
  { value: "system",     labelKey: "notif_cat_system",    color: "text-purple-400",  bg: "bg-purple-500/15",  border: "border-purple-500/40" },
  { value: "permanent",  labelKey: "notif_cat_permanent", color: "text-danger",      bg: "bg-danger/15",      border: "border-danger/40" },
];

// 分类展示标签 i18n key 映射
// 注：inbox 类别在 i18n.py 中暂无对应 key（notif_cat_inbox 不存在），
// 因此 inbox 保持硬编码中文 "收件箱"，其余类别走 tr() 解析
const CATEGORY_LABEL_KEY: Record<string, string> = {
  deps: "notif_cat_deps",
  env: "notif_cat_env",
  update: "notif_cat_update",
  system: "notif_cat_system",
};

// inbox 类别无 i18n key，保留原文
const CATEGORY_LABEL_FALLBACK: Record<string, string> = {
  inbox: "收件箱",
};

// 分类色（图标圆圈背景/边框/颜色）
const CATEGORY_COLOR: Record<
  string,
  { text: string; bg: string; border: string }
> = {
  deps:   { text: "text-warning",    bg: "bg-warning/15",    border: "border-warning/30" },
  env:    { text: "text-info",       bg: "bg-info/15",       border: "border-info/30" },
  update: { text: "text-success",    bg: "bg-success/15",    border: "border-success/30" },
  system: { text: "text-purple-400", bg: "bg-purple-500/15", border: "border-purple-500/30" },
  inbox:  { text: "text-accent",     bg: "bg-accent/15",     border: "border-accent/30" },
};

function categoryStyle(c: string) {
  return (
    CATEGORY_COLOR[c] || {
      text: "text-text-muted",
      bg: "bg-white/10",
      border: "border-white/20",
    }
  );
}

// 优先级颜色（用于 badge 文字色）
// 注：priorityColor 原函数已合并到 badge 渲染逻辑中，此处保留注释说明

// 优先级左边条颜色
function priorityBarClass(p: string): string {
  if (p === "critical") return "bg-danger";
  if (p === "high") return "bg-warning";
  return "";
}

// 类型图标（用 emoji 简化，避免依赖 icon 集）
function typeIcon(t: string): string {
  if (t === "warning") return "⚠";
  if (t === "update") return "↻";
  if (t === "tip") return "ℹ";
  return "ℹ";
}

// 时间格式化：2026-07-27T10:30:45.123456+00:00 → "2026-07-27 10:30:45"
function formatTime(t: string): string {
  if (!t || t.length === 0) return "—";
  return t.replace("T", " ").substring(0, 19);
}

// 优先级排序权重
const PRIORITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  normal: 2,
  low: 3,
};

// ============================================================
// 主组件
// ============================================================

export function NotificationsPage() {
  const navigate = useNav();
  const { tr } = useI18n();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  // —— 拉取数据 ——
  const reload = useCallback(async () => {
    try {
      const data = await api.getNotifications();
      setItems(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // —— WebSocket 事件订阅 ——
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      if (e.type === "notification_changed") {
        reload();
      }
    });
    return unsub;
  }, [reload]);

  // —— 客户端筛选 + 优先级排序（与 QML _applyFilter 对齐） ——
  const filtered = useMemo(() => {
    const out: NotificationItem[] = [];
    for (const n of items) {
      if (filter === "all") {
        out.push(n);
      } else if (filter === "permanent") {
        // permanent 筛选 = 所有 dismissable=false 的通知
        if (!n.dismissable) out.push(n);
      } else {
        if (n.category === filter && n.dismissable) out.push(n);
      }
    }
    // 按优先级排序：critical > high > normal > low（同级保持插入顺序）
    out.sort((a, b) => {
      const pa = PRIORITY_ORDER[a.priority] ?? 2;
      const pb = PRIORITY_ORDER[b.priority] ?? 2;
      return pa - pb;
    });
    return out;
  }, [items, filter]);

  // —— 统计 ——
  const unreadCount = useMemo(
    () => items.filter((n) => !n.read).length,
    [items]
  );

  // —— 操作 ——
  const onMarkAllRead = useCallback(async () => {
    try {
      await api.markAllRead();
      // 后端会推 notification_changed 触发 reload
    } catch (e) {
      console.warn("mark all read failed:", e);
    }
  }, []);

  const onClearRead = useCallback(async () => {
    try {
      await api.clearRead();
      // 后端会推 notification_changed
    } catch (e) {
      console.warn("clear read failed:", e);
    }
  }, []);

  const onMarkRead = useCallback(async (id: string) => {
    try {
      await api.markRead(id);
      // 后端会推 notification_changed
    } catch (e) {
      console.warn("mark read failed:", e);
    }
  }, []);

  const onDismiss = useCallback(async (id: string) => {
    try {
      await api.dismiss(id);
      // 后端会推 notification_changed
    } catch (e) {
      console.warn("dismiss failed:", e);
    }
  }, []);

  const onAction = useCallback(
    (action: string) => {
      if (!action) return;
      if (action.startsWith("open_url:")) {
        const url = action.substring("open_url:".length);
        api.openExternalUrl(url).catch((e) =>
          console.warn("open external url failed:", e)
        );
      } else if (action.startsWith("open_page:")) {
        // 切换到对应页面（如 "open_page:settings" → 切到 Settings tab）
        const page = action.substring("open_page:".length);
        navigate(page);
      }
      // retry_task: 等其他 action 暂未实现
    },
    [navigate]
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
          {/* 注：i18n.py 暂无 "加载失败" 对应 key，保留原文 */}
          <h2 className="text-lg font-semibold text-danger">{tr("load_failed")}</h2>
          <p className="mt-2 text-sm text-text-muted">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto px-8 py-6">
      {/* ============================================================ */}
      {/* Header：标题 + badge + 操作按钮 */}
      {/* ============================================================ */}
      <header className="mb-6 flex items-center gap-4">
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{tr("notifications_page")}</h1>
          <p className="mt-1 text-sm text-text-muted">
            {tr("notifications_subtitle")}
          </p>
        </div>

        {/* 未读 badge */}
        <div className="rounded-full border border-accent/30 bg-accent/10 px-3 py-1">
          <span className="font-mono text-xs font-semibold text-accent">
            {tr("notif_unread_count", { n: unreadCount, total: items.length })}
          </span>
        </div>

        <button
          onClick={onMarkAllRead}
          disabled={items.length === 0}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm font-medium text-text transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {tr("mark_all_read")}
        </button>
        <button
          onClick={onClearRead}
          disabled={items.length === 0}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/5 hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
        >
          {tr("notif_clear_read")}
        </button>
      </header>

      {/* ============================================================ */}
      {/* 分类筛选（segmented control 风格） */}
      {/* ============================================================ */}
      <div className="mb-6 flex items-center gap-1 rounded-xl border border-white/5 bg-white/[0.03] p-1">
        {FILTER_OPTIONS.map((opt) => {
          const active = filter === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                active
                  ? `${opt.bg} ${opt.color} border ${opt.border}`
                  : "text-text-muted hover:bg-white/5 hover:text-text border border-transparent"
              }`}
            >
              {opt.value !== "all" && (
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    active ? `bg-current` : "bg-current opacity-50"
                  }`}
                />
              )}
              {tr(opt.labelKey)}
            </button>
          );
        })}
      </div>

      {/* ============================================================ */}
      {/* 空状态 */}
      {/* ============================================================ */}
      {items.length === 0 && (
        <div className="mt-20 text-center text-text-muted">{tr("no_notifications")}</div>
      )}

      {/* ============================================================ */}
      {/* 通知列表 */}
      {/* ============================================================ */}
      <div className="space-y-3">
        {filtered.map((n) => {
          const cs = categoryStyle(n.category);
          const isCritical = n.priority === "critical";
          const isHigh = n.priority === "high";
          const isLow = n.priority === "low";
          const showPriorityBar = isCritical || isHigh;

          return (
            <div
              key={n.id}
              onClick={() => {
                if (!n.read) onMarkRead(n.id);
              }}
              className={`glass-card group relative flex cursor-pointer items-start gap-4 overflow-hidden p-5 transition-colors ${
                n.read ? "opacity-80" : ""
              } ${isLow ? "opacity-70" : ""} hover:bg-white/[0.06]`}
            >
              {/* 优先级左边条（critical/high） */}
              {showPriorityBar && (
                <div
                  className={`absolute left-2 top-2 bottom-2 w-[3px] rounded-full ${priorityBarClass(
                    n.priority
                  )} ${isCritical ? "opacity-100" : "opacity-70"}`}
                />
              )}

              {/* 永久通知左边 indicator（替代优先级条，不可关闭时显示） */}
              {!n.dismissable && !showPriorityBar && (
                <div className="absolute left-2 top-2 bottom-2 w-1 rounded-full bg-danger/60" />
              )}

              {/* 类型图标圆圈 */}
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border ${cs.bg} ${cs.border} ${cs.text} ${
                  isLow ? "h-8 w-8 text-xs" : "text-base"
                }`}
                style={{ marginLeft: showPriorityBar || !n.dismissable ? 8 : 0 }}
              >
                <span>{typeIcon(n.type)}</span>
              </div>

              {/* 内容区 */}
              <div className="min-w-0 flex-1">
                {/* 标题行 */}
                <div className="flex flex-wrap items-center gap-2">
                  <h3
                    className={`text-sm font-semibold ${
                      n.read ? "text-text-muted" : "text-text"
                    }`}
                  >
                    {n.title}
                  </h3>

                  {/* 优先级 badge */}
                  {(isCritical || isHigh) && (
                    <span
                      className={`rounded border ${
                        isCritical
                          ? "border-danger/30 bg-danger/10 text-danger"
                          : "border-warning/30 bg-warning/10 text-warning"
                      } px-1.5 py-0.5 font-mono text-[9px] font-bold`}
                    >
                      {isCritical ? "CRITICAL" : "HIGH"}
                    </span>
                  )}

                  {/* 分类 badge */}
                  <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-text-muted">
                    {CATEGORY_LABEL_KEY[n.category]
                      ? tr(CATEGORY_LABEL_KEY[n.category])
                      : CATEGORY_LABEL_FALLBACK[n.category] || n.category}
                  </span>

                  {/* 时间 */}
                  <span className="ml-auto font-mono text-[10px] text-text-dim">
                    {formatTime(n.created_at)}
                  </span>
                </div>

                {/* 消息正文 */}
                {n.message && (
                  <p
                    className={`mt-1 text-sm text-text-muted ${
                      isLow ? "opacity-70" : ""
                    }`}
                  >
                    {n.message}
                  </p>
                )}

                {/* Action 按钮 */}
                {n.action_text && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onAction(n.action);
                    }}
                    className="mt-2 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
                  >
                    {n.action_text}
                    <span>↗</span>
                  </button>
                )}
              </div>

              {/* 右侧：未读红点 + 关闭/锁图标 */}
              <div className="flex shrink-0 flex-col items-center gap-2">
                {/* 未读小红点 */}
                {!n.read && (
                  <span className="h-2 w-2 rounded-full bg-accent opacity-90" />
                )}

                <div className="flex-1" />

                {/* 关闭按钮（可关闭的通知） */}
                {n.dismissable ? (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDismiss(n.id);
                    }}
                    title={tr("close")}
                    className="flex h-6 w-6 items-center justify-center rounded text-text-muted opacity-0 transition-opacity hover:bg-white/10 hover:text-text group-hover:opacity-100"
                  >
                    ✕
                  </button>
                ) : (
                  /* 永久通知的锁图标 */
                  <div
                    title={tr("notif_permanent_locked")}
                    className="flex h-6 w-6 cursor-help items-center justify-center rounded border border-white/10 text-text-dim"
                  >
                    <span className="text-[10px]">🔒</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="h-12" />
    </div>
  );
}
