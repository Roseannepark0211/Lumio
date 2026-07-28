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
import { useI18n } from "../i18n";
import { formatSize as formatSizeRaw } from "../utils/format";
import { platformLabel, platformDotColor } from "../utils/platform";

// ============================================================
// 常量
// ============================================================

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
  return formatSizeRaw(bytes, true);
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
  const { tr } = useI18n();

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
        label: tr("stats_total"),
        value: stats.total_downloads.toString(),
        accent: "text-accent",
      },
      {
        label: tr("stats_size"),
        value: formatSize(stats.total_size),
        accent: "text-success",
      },
      {
        label: tr("stats_success_rate"),
        value: (stats.success_rate || 0).toFixed(1) + "%",
        accent: "text-warning",
      },
      {
        label: tr("stats_today"),
        value: stats.today_count.toString(),
        accent: "text-pink-400",
      },
    ],
    [stats, tr]
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
            <h1 className="text-xl font-bold text-text">{tr("stats")}</h1>
            <p className="mt-0.5 text-xs text-text-muted">
              {tr("stats_subtitle")}
            </p>
          </div>
          <button
            onClick={() => reload()}
            className="flex items-center gap-1.5 rounded-lg bg-white/5 px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            title={tr("inbox_refresh")}
          >
            ↻ {tr("inbox_refresh")}
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
                    {platformLabel(p.platform, tr)}
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
