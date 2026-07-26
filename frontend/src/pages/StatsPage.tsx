/**
 * React StatsPage — 复刻 QML StatsPage.qml 完整功能。
 *
 * 功能清单（与 QML 版本对齐）：
 *   1. 4 张主统计卡：总下载数 / 总下载体积 / 成功率 / 今日下载
 *   2. 平台分布卡（3 列网格，按数量降序排列，圆点+名称+次数+大数字）
 *   3. 空状态提示（total_downloads === 0 时显示）
 *   4. WebSocket 事件驱动刷新（history_changed / history_record_added）
 *
 * 与 QML 版本差异：
 *   - 平台分布排序在前端做（QML 用 _platformsArray()，React 用 useMemo + sort）
 *   - 平台颜色/标签用本地常量（与 LibraryPage / HistoryPage 同款风格）
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import {
  api,
  subscribeEvents,
  type AppEvent,
  type StatsResponse,
} from "../api";

// ============================================================
// 常量
// ============================================================

// 平台展示名（与 LibraryPage / HistoryPage 对齐）
const PLATFORM_LABEL: Record<string, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
  x: "X",
  bilibili: "B站",
  douyin: "抖音",
  kuaishou: "快手",
  weibo: "微博",
  xiaohongshu: "小红书",
  telegram: "Telegram",
  unknown: "未知",
};

function platformLabel(p: string): string {
  return PLATFORM_LABEL[p] || (p ? p.toUpperCase() : "未知");
}

// 平台圆点颜色（与 QML Theme.platformColor 对齐）
const PLATFORM_DOT_COLOR: Record<string, string> = {
  youtube: "bg-red-500",
  instagram: "bg-pink-500",
  x: "bg-zinc-200",
  bilibili: "bg-blue-500",
  douyin: "bg-zinc-100",
  kuaishou: "bg-orange-500",
  weibo: "bg-orange-600",
  xiaohongshu: "bg-red-600",
  telegram: "bg-sky-500",
  unknown: "bg-zinc-500",
};

function platformDotColor(p: string): string {
  return PLATFORM_DOT_COLOR[p] || "bg-zinc-500";
}

// 平台大数字色（与 QML 实现 text=platformColor 对齐，偏冷调暗色）
const PLATFORM_TEXT_COLOR: Record<string, string> = {
  youtube: "text-red-400",
  instagram: "text-pink-400",
  x: "text-zinc-200",
  bilibili: "text-blue-400",
  douyin: "text-zinc-100",
  kuaishou: "text-orange-400",
  weibo: "text-orange-500",
  xiaohongshu: "text-red-500",
  telegram: "text-sky-400",
  unknown: "text-text-muted",
};

function platformTextColor(p: string): string {
  return PLATFORM_TEXT_COLOR[p] || "text-text-muted";
}

function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

// ============================================================
// 主组件
// ============================================================

const EMPTY_STATS: StatsResponse = {
  total_downloads: 0,
  total_size: 0,
  success_rate: 0.0,
  today_count: 0,
  platforms: {},
};

export function StatsPage() {
  // —— 数据状态 ——
  const [stats, setStats] = useState<StatsResponse>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // —— 拉取数据 ——
  const reload = useCallback(async () => {
    try {
      const s = await api.getStats();
      setStats(s);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // —— 初次加载 ——
  useEffect(() => {
    reload();
  }, [reload]);

  // —— WebSocket 事件订阅（与 QML onHistoryChanged 对齐）——
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      // 历史记录变化时刷新统计
      if (e.type === "history_changed" || e.type === "history_record_added") {
        reload();
      }
    });
    return unsub;
  }, [reload]);

  // —— 平台分布数组（按数量降序，与 QML _platformsArray 对齐）——
  const platformsArray = useMemo(() => {
    const p = stats.platforms || {};
    const arr: { platform: string; count: number }[] = [];
    for (const k of Object.keys(p)) {
      arr.push({ platform: k, count: p[k] });
    }
    arr.sort((a, b) => b.count - a.count);
    return arr;
  }, [stats.platforms]);

  // —— 4 张主卡数据 ——
  const mainCards = useMemo(
    () => [
      {
        label: "总下载",
        value: stats.total_downloads.toString(),
        accent: "text-accent",
      },
      {
        label: "下载体积",
        value: formatSize(stats.total_size),
        accent: "text-success",
      },
      {
        label: "成功率",
        value: (stats.success_rate || 0).toFixed(1) + "%",
        accent: "text-warning",
      },
      {
        label: "今日下载",
        value: stats.today_count.toString(),
        accent: "text-pink-400",
      },
    ],
    [stats]
  );

  // —— 渲染 ——
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-text-muted">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="glass-card max-w-md p-6">
          <h2 className="text-lg font-semibold text-danger">加载失败</h2>
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
            <h1 className="text-xl font-bold text-text">统计</h1>
            <p className="mt-0.5 text-xs text-text-muted">
              总览下载量、成功率与平台分布
            </p>
          </div>
          <button
            onClick={() => reload()}
            className="flex items-center gap-1.5 rounded-lg bg-white/5 px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            title="刷新"
          >
            ↻ 刷新
          </button>
        </header>

        {/* 4 张主统计卡 */}
        <div className="grid grid-cols-2 gap-3.5 md:grid-cols-4">
          {mainCards.map((c) => (
            <div
              key={c.label}
              className="glass-card flex h-[110px] flex-col justify-center gap-1 p-[18px]"
            >
              <div className="font-mono text-[11px] tracking-wide text-text-muted">
                {c.label}
              </div>
              <div className={`text-[28px] font-bold ${c.accent}`}>
                {c.value}
              </div>
            </div>
          ))}
        </div>

        {/* 平台分布标题 */}
        <h2 className="mt-3 text-base font-bold text-text">平台分布</h2>

        {/* 平台分布卡（3 列网格） */}
        {platformsArray.length > 0 ? (
          <div className="grid grid-cols-1 gap-3.5 md:grid-cols-3">
            {platformsArray.map((p) => (
              <div
                key={p.platform}
                className="glass-card flex h-[80px] items-center gap-3.5 p-[18px]"
              >
                {/* 平台圆点 */}
                <div
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${platformDotColor(
                    p.platform
                  )}`}
                />
                {/* 平台名 + 次数小字 */}
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <div className="truncate text-sm font-semibold text-text">
                    {platformLabel(p.platform)}
                  </div>
                  <div className="font-mono text-[11px] text-text-muted">
                    {p.count} 次下载
                  </div>
                </div>
                {/* 大数字 */}
                <div
                  className={`shrink-0 text-[22px] font-bold ${platformTextColor(
                    p.platform
                  )}`}
                >
                  {p.count}
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {/* 空状态 */}
        {stats.total_downloads === 0 && (
          <div className="mt-10 text-center text-sm text-text-muted">
            暂无下载记录
          </div>
        )}

        {/* 底部 spacer */}
        <div className="h-12" />
      </div>
    </div>
  );
}
