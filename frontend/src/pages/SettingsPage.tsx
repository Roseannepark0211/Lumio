/**
 * React SettingsPage — 复刻 QML SettingsPage.qml 完整功能。
 *
 * 功能分组：
 *   1. 账号
 *      - Cookie 管理：导入/清除、总状态、8 平台单独状态
 *      - Apify 代理：启用开关、Token、Actor ID、验证、连接状态、月度用量
 *      - Telegram：启用、Token、API 地址、配对码、绑定设备
 *   2. 下载
 *      - 下载设置：目录、存储模式、冲突策略、并发数、重试次数
 *      - 缓存管理：4 目录统计、立即清理、强制清空、自动模式、保留天数、容量上限
 *   3. 系统
 *      - 通用：语言、主题、自动下载收件箱、X-Sou 开关
 *      - 关于：版本号、检查更新
 *
 * 与 QML 版本差异：
 *   - 文件/文件夹对话框走 Electron IPC（dialog.showOpenDialog），
 *     而非 QML 的 controller.browseFolder/browseCookieFile（QFileDialog）
 *   - tr() 翻译改为直接中文文案
 *   - 颜色用 Tailwind class 替代 Theme.xxx
 */

import { useEffect, useState, useCallback, useRef } from "react";
import {
  api,
  subscribeEvents,
  type AppEvent,
  type CookieStatusResponse,
  type TelegramState,
  type ApifyStatus,
  type ApifyUsage,
  type CacheStats,
  type CheckUpdateResult,
} from "../api";
import { useToast } from "../App";

// ============================================================
// 常量
// ============================================================

// 8 个平台 cookie 状态展示
const PLATFORM_COOKIE_LIST: { key: string; label: string }[] = [
  { key: "instagram", label: "Instagram" },
  { key: "x", label: "X" },
  { key: "youtube", label: "YouTube" },
  { key: "weibo", label: "微博" },
  { key: "douyin", label: "抖音" },
  { key: "xiaohongshu", label: "小红书" },
  { key: "bilibili", label: "B站" },
  { key: "kuaishou", label: "快手" },
];

// 存储模式
const STORAGE_MODES = [
  { value: "simple", label: "简单（直接平铺）" },
  { value: "organized", label: "结构化（按平台分目录）" },
];

// 文件冲突策略
const CONFLICT_POLICIES = [
  { value: "rename", label: "重命名（添加 (1) 后缀）" },
  { value: "skip", label: "跳过已存在文件" },
  { value: "overwrite", label: "覆盖原文件" },
  { value: "ask", label: "每次询问" },
];

// 自动清理模式
const AUTO_CLEAN_MODES = [
  { value: "off", label: "关闭" },
  { value: "startup", label: "每次启动" },
  { value: "daily", label: "每天" },
  { value: "weekly", label: "每周" },
];

const LANGS = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
];

const THEMES = [
  { value: "dark", label: "深色" },
  { value: "light", label: "浅色" },
];

const COOKIE_FILTER = [{ name: "Cookie Files", extensions: ["txt"] }];

// ============================================================
// 主组件
// ============================================================

export function SettingsPage() {
  // —— 配置 / 状态 ——
  const [config, setConfig] = useState<Record<string, any>>({});
  const [cookieStatus, setCookieStatus] = useState<CookieStatusResponse | null>(null);
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [tgState, setTgState] = useState<TelegramState | null>(null);
  const [apifyState, setApifyState] = useState<ApifyStatus | null>(null);
  const [apifyUsage, setApifyUsage] = useState<ApifyUsage>({});
  const [updateStatus, setUpdateStatus] = useState("");

  // —— 验证瞬态 ——
  const [tgValidating, setTgValidating] = useState(false);
  const [tgValidateMsg, setTgValidateMsg] = useState("");
  const [apifyValidating, setApifyValidating] = useState(false);
  const [apifyValidateMsg, setApifyValidateMsg] = useState("");

  // —— 加载 / 错误 ——
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // —— 对话框 ——
  const [confirmCookieClear, setConfirmCookieClear] = useState(false);
  const [confirmForceClear, setConfirmForceClear] = useState(false);
  const [confirmTgUnlink, setConfirmTgUnlink] = useState(false);

  // 在事件回调中引用最新 apifyState（避免闭包陈旧）
  const apifyStateRef = useRef<ApifyStatus | null>(null);
  apifyStateRef.current = apifyState;

  // —— 拉取数据 ——
  const reload = useCallback(async () => {
    try {
      const [cfg, cs, ts, as, cache] = await Promise.all([
        api.getConfig(),
        api.getCookieStatus().catch(() => null),
        api.getTelegramState().catch(() => null),
        api.getApifyStatus().catch(() => null),
        api.getCacheStats().catch(() => null),
      ]);
      setConfig(cfg);
      setCookieStatus(cs);
      setTgState(ts);
      setApifyState(as);
      setCacheStats(cache);

      // Apify 已连接时同步用量（首次 / 缓存命中）
      if (as?.connected && as.usage_usd != null) {
        setApifyUsage({
          usage_usd: as.usage_usd,
          plan_credits_usd: as.plan_credits_usd ?? undefined,
          plan_name: as.plan_name ?? undefined,
          usage_updated: as.usage_updated ?? undefined,
        });
      }

      // 后台刷新用量（5 分钟内不重复）
      if (as?.connected) {
        api.refreshApifyUsage().catch(() => {});
      }

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
      switch (e.type) {
        case "config_changed":
          // 配置变化 → 重新拉取
          reload();
          break;
        case "apify_usage_updated":
          setApifyUsage((e.data as ApifyUsage) || {});
          break;
        case "cache_cleaned":
          // 清理完成 → 重新拉取统计
          api.getCacheStats().then(setCacheStats).catch(() => {});
          break;
        case "theme_changed":
        case "lang_changed":
          // 主题/语言切换由全局处理，这里只刷新 config
          api.getConfig().then(setConfig).catch(() => {});
          break;
        default:
          break;
      }
    });
    return unsub;
  }, [reload]);

  // —— 工具函数 ——
  // 用全局 toast（App.tsx 监听 WS toast 事件统一渲染），不再调 api.showToast 走后端回环
  const showToast = useToast();

  const saveConfig = useCallback(
    async (key: string, value: unknown) => {
      try {
        await api.setConfig(key, value);
      } catch (e) {
        showToast(`保存失败: ${e}`);
      }
    },
    [showToast]
  );

  const saveNestedConfig = useCallback(
    async (parentKey: string, updates: Record<string, unknown>) => {
      try {
        await api.setNestedConfig(parentKey, updates);
      } catch (e) {
        showToast(`保存失败: ${e}`);
      }
    },
    [showToast]
  );

  // —— Cookie 操作 ——
  const onImportCookie = useCallback(async () => {
    try {
      const paths = await api.pickFiles(COOKIE_FILTER);
      if (paths.length === 0) {
        showToast("未选择文件");
        return;
      }
      const r = await api.importCookie(paths);
      if (r.ok) {
        showToast(`已导入 ${r.imported ?? paths.length} 个 cookie 文件`);
        // 刷新状态
        const cs = await api.getCookieStatus();
        setCookieStatus(cs);
      } else {
        showToast(r.error || "导入失败");
      }
    } catch (e) {
      showToast(`导入失败: ${e}`);
    }
  }, [showToast]);

  const onClearCookie = useCallback(async () => {
    setConfirmCookieClear(false);
    try {
      const r = await api.clearCookie();
      if (r.ok) {
        showToast("已清除 cookie");
        const cs = await api.getCookieStatus();
        setCookieStatus(cs);
      } else {
        showToast(r.error || "清除失败");
      }
    } catch (e) {
      showToast(`清除失败: ${e}`);
    }
  }, [showToast]);

  // —— Telegram 操作 ——
  const onValidateTelegram = useCallback(async () => {
    if (tgValidating) return;
    const tokenInput = (document.getElementById("tg-token-input") as HTMLInputElement)?.value || "";
    // config.telegram_bot_token 在后端被脱敏为 "***configured***"，不能用作真实 token。
    // 用户必须输入新 token 才能验证（占位符 ••• 或空都视为未输入）。
    const token = tokenInput === "••••••••••••••••" ? "" : tokenInput.trim();
    if (!token) {
      setTgValidateMsg("请先输入 Token");
      return;
    }
    setTgValidating(true);
    setTgValidateMsg("验证中...");
    try {
      const r = await api.validateTelegram(token, config.http_proxy || "");
      if (r.ok) {
        setTgValidateMsg(`✅ 验证成功：@${r.username || ""}`);
        // 验证成功才保存 token（失败不保存，避免覆盖旧的有效 token）
        await saveConfig("telegram_bot_token", token);
        // 重新生成配对码
        await api.getTelegramPairCode();
        const ts = await api.getTelegramState();
        setTgState(ts);
      } else {
        setTgValidateMsg(`❌ 验证失败：${r.error || ""}`);
      }
    } catch (e) {
      setTgValidateMsg(`❌ 验证失败：${e}`);
    } finally {
      setTgValidating(false);
    }
  }, [tgValidating, config.http_proxy, saveConfig]);

  const onCopyPairCode = useCallback(async () => {
    const code = tgState?.pair_code || "";
    if (!code) return;
    try {
      await api.copyToClipboard(code);
      showToast("配对码已复制");
    } catch (e) {
      console.warn("copy failed:", e);
    }
  }, [tgState, showToast]);

  const onRegenPairCode = useCallback(async () => {
    try {
      await api.getTelegramPairCode();
      const ts = await api.getTelegramState();
      setTgState(ts);
    } catch (e) {
      console.warn("regen pair code failed:", e);
    }
  }, []);

  const onUnlinkTelegram = useCallback(async () => {
    setConfirmTgUnlink(false);
    try {
      const r = await api.unlinkTelegram();
      if (r.ok) {
        showToast("已解除 Telegram 绑定");
        const ts = await api.getTelegramState();
        setTgState(ts);
      } else {
        showToast(r.error || "解绑失败");
      }
    } catch (e) {
      showToast(`解绑失败: ${e}`);
    }
  }, [showToast]);

  // —— Apify 操作 ——
  const onValidateApify = useCallback(async () => {
    if (apifyValidating) return;
    const tokenInput = (document.getElementById("apify-token-input") as HTMLInputElement)?.value || "";
    // config.apify_token 在后端被脱敏（"apify_api_..." 形式），不能用作真实 token。
    // 占位符 ••• 视为未输入；用户新输入的 token（即使以 apify_api_ 开头）直接使用。
    const token = tokenInput === "••••••••••••••••" ? "" : tokenInput.trim();
    const actorInput = (document.getElementById("apify-actor-input") as HTMLInputElement)?.value || "";
    const actor = actorInput.trim() || (config.apify_ig_actor || "");
    if (!token) {
      setApifyValidateMsg("请先输入 Token");
      return;
    }
    if (!actor) {
      setApifyValidateMsg("请先输入 Actor ID");
      return;
    }
    setApifyValidating(true);
    setApifyValidateMsg("验证中...");
    try {
      const r = await api.validateApify(token, actor);
      if (r.ok) {
        setApifyValidateMsg("✅ 已连接");
        const as = await api.getApifyStatus();
        setApifyState(as);
        // 强制刷新用量
        api.forceRefreshApifyUsage().catch(() => {});
      } else {
        setApifyValidateMsg(`❌ ${r.error || "验证失败"}`);
        // 验证失败也刷新状态（后端可能已清除 apify_verified）
        const as = await api.getApifyStatus();
        setApifyState(as);
      }
    } catch (e) {
      setApifyValidateMsg(`❌ ${e}`);
      const as = await api.getApifyStatus().catch(() => null);
      if (as) setApifyState(as);
    } finally {
      setApifyValidating(false);
    }
  }, [apifyValidating, config.apify_ig_actor, showToast]);

  const onForceRefreshApify = useCallback(async () => {
    setApifyUsage({});
    try {
      await api.forceRefreshApifyUsage();
      // WS apify_usage_updated 会推送结果
    } catch (e) {
      console.warn("force refresh failed:", e);
    }
  }, []);

  // —— 下载目录浏览 ——
  const onBrowseDownloadDir = useCallback(async () => {
    try {
      const folder = await api.pickFolder();
      if (folder) {
        await saveConfig("download_dir", folder);
        showToast(`已设置下载目录: ${folder}`);
      } else {
        showToast("未选择文件夹");
      }
    } catch (e) {
      showToast(`打开对话框失败: ${e}`);
    }
  }, [saveConfig, showToast]);

  // —— 缓存操作 ——
  const onCleanByRules = useCallback(async () => {
    try {
      await api.cleanCacheByRules();
      showToast("已触发按规则清理");
      // WS cache_cleaned 会推送结果，触发刷新
    } catch (e) {
      showToast(`清理失败: ${e}`);
    }
  }, [showToast]);

  const onForceClear = useCallback(async () => {
    setConfirmForceClear(false);
    try {
      await api.forceClearCache();
      showToast("已触发强制清空");
    } catch (e) {
      showToast(`清空失败: ${e}`);
    }
  }, [showToast]);

  // —— 检查更新 ——
  const onCheckUpdate = useCallback(async () => {
    setUpdateStatus("检查中...");
    try {
      const r: CheckUpdateResult = await api.checkUpdate();
      if (r.error) {
        setUpdateStatus(`❌ 检查失败：${r.error}`);
      } else if (r.has_update) {
        setUpdateStatus(`🆕 发现新版本：v${r.latest}（当前 v${r.current}）`);
      } else {
        setUpdateStatus(`✅ 已是最新版本 v${r.current}`);
      }
    } catch (e) {
      setUpdateStatus(`❌ 检查失败：${e}`);
    }
  }, []);

  // —— 主题 / 语言切换 ——
  const onSetTheme = useCallback(
    async (theme: string) => {
      try {
        await api.setTheme(theme);
      } catch (e) {
        showToast(`主题切换失败: ${e}`);
      }
    },
    [showToast]
  );

  const onSetLang = useCallback(
    async (lang: string) => {
      try {
        await api.setLang(lang);
      } catch (e) {
        showToast(`语言切换失败: ${e}`);
      }
    },
    [showToast]
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

  // —— 派生数据 ——
  // 注意：不能在早返回（loading/error）之后调用 useMemo/useEffect 等 hook，
  // 否则 "Rendered more hooks than during the previous render" 报错。
  const cacheMgmt = (config.cache_management || {}) as Record<string, any>;
  const totalCacheSize = (() => {
    if (!cacheStats) return 0;
    let total = 0;
    for (const k of Object.keys(cacheStats)) {
      if (k.startsWith("_") || k === "error") continue;
      const s = (cacheStats as any)[k] as { size_bytes?: number };
      if (s?.size_bytes) total += s.size_bytes;
    }
    return total;
  })();

  const cacheRootPath = (cacheStats?._root as string) || "";

  return (
    <div className="h-full overflow-y-auto">
      <div className="flex flex-col gap-5 p-6 pb-12">
        {/* ============================================================ */}
        {/* PageHeader */}
        {/* ============================================================ */}
        <header className="animate-slide-up">
          <h1 className="text-xl font-bold text-text">设置</h1>
          <p className="mt-0.5 text-xs text-text-muted">
            账号 / 下载 / 系统 — 调整 Lumio 行为
          </p>
        </header>

        {/* ============================================================ */}
        {/* 分组：账号 */}
        {/* ============================================================ */}
        <SectionLabel>账号</SectionLabel>

        {/* ---------- Cookie 管理 ---------- */}
        <SettingsCard
          icon="🍪"
          iconColor="text-warning"
          title="Cookie 管理"
          desc="IG / X / 微博等平台访问凭证"
        >
          <Row label="状态">
            <StatusBadge status={cookieStatus?.overall || "missing"} />
            <div className="flex-1" />
            <button
              onClick={() => setConfirmCookieClear(true)}
              className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-white/5 hover:text-text"
            >
              🗑 清除
            </button>
            <button
              onClick={onImportCookie}
              className="rounded-lg bg-accent/15 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/25"
            >
              ↓ 导入
            </button>
          </Row>

          {/* Cookie 文件路径 */}
          <div className="truncate font-mono text-[10px] text-text-dim">
            {(config.cookie_file as string) || "—"}
          </div>

          {/* 各平台单独状态 */}
          <div className="mt-2 text-[10px] uppercase tracking-wider text-text-muted">
            各平台状态
          </div>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
            {PLATFORM_COOKIE_LIST.map((p) => {
              const s =
                (cookieStatus?.platforms?.[p.key] as string) || "missing";
              const color =
                s === "valid"
                  ? "text-success"
                  : s === "warning"
                  ? "text-warning"
                  : s === "expired"
                  ? "text-danger"
                  : "text-text-dim";
              const icon =
                s === "valid" ? "✓" : s === "warning" ? "!" : s === "expired" ? "✗" : "—";
              return (
                <div
                  key={p.key}
                  className="flex items-center gap-2 rounded-md border border-white/10 bg-white/5 px-2 py-1.5"
                >
                  <span
                    className={`inline-block h-1.5 w-1.5 rounded-full ${
                      s === "valid"
                        ? "bg-success"
                        : s === "warning"
                        ? "bg-warning"
                        : s === "expired"
                        ? "bg-danger"
                        : "bg-white/30"
                    }`}
                  />
                  <span className="flex-1 text-[11px] text-text">{p.label}</span>
                  <span className={`text-xs font-bold ${color}`}>{icon}</span>
                </div>
              );
            })}
          </div>
        </SettingsCard>

        {/* ---------- Apify 代理 ---------- */}
        <SettingsCard
          icon="✨"
          iconColor="text-pink-400"
          title="Apify 代理（Instagram API）"
          desc="通过 Apify Actor 代理提取 IG 数据，避免账号风控"
        >
          <Row label="启用">
            <Switch
              checked={config.instagram_mode === "api"}
              onChange={(v) => saveConfig("instagram_mode", v ? "api" : "cookie")}
            />
            <span
              className={`ml-2 rounded border px-2 py-0.5 text-[10px] font-medium ${
                config.instagram_mode === "api"
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-white/10 bg-white/5 text-text-muted"
              }`}
            >
              {config.instagram_mode === "api" ? "已启用" : "未启用"}
            </span>
          </Row>
          <p className="text-[10px] text-text-dim">
            启用后 Instagram 走 Apify 代理路径；不启用则使用本地 Cookie 模式调移动 API
          </p>

          {/* —— 折叠区：仅在启用时展开 —— */}
          {config.instagram_mode === "api" && (
            <>
              <Row label="Apify Token">
                <input
                  id="apify-token-input"
                  type="password"
                  placeholder="apify_api_..."
                  defaultValue={
                    apifyState?.token_configured ? "••••••••••••••••" : ""
                  }
                  className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
                />
                <button
                  onClick={onValidateApify}
                  disabled={apifyValidating}
                  className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-medium text-text hover:bg-white/15 disabled:opacity-40"
                >
                  {apifyValidating ? "验证中..." : "验证"}
                </button>
              </Row>

              <Row label="Actor ID">
                <input
                  id="apify-actor-input"
                  type="text"
                  placeholder="shu8hvrXbJbY3Eb9W"
                  defaultValue={apifyState?.actor_id || ""}
                  onBlur={(e) => {
                    const v = e.target.value;
                    if (v) saveConfig("apify_ig_actor", v);
                  }}
                  className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
                />
              </Row>

              {/* 验证状态瞬态 */}
              {/* 已连接持久态显示时隐藏瞬态（避免"✅已连接"和持久徽章同时出现，对齐 QML 版） */}
              {apifyValidateMsg &&
                !(apifyValidateMsg.startsWith("✅") && apifyState?.connected) && (
                  <p
                    className={`text-xs ${
                      apifyValidateMsg.startsWith("✅") ? "text-success" : "text-danger"
                    }`}
                  >
                    {apifyValidateMsg}
                  </p>
                )}

              {/* 持久连接状态 */}
              <div className="flex items-center gap-2">
                {apifyState?.token_configured && apifyState?.actor_configured ? (
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                      apifyState.connected
                        ? "border-success/30 bg-success/10 text-success"
                        : "border-warning/30 bg-warning/10 text-warning"
                    }`}
                  >
                    ● {apifyState.connected ? "已连接" : "待验证"}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-medium text-text-muted">
                    ● 未配置
                  </span>
                )}
              </div>

              {/* 月度用量条 */}
              {apifyState?.connected && (
            <div className="rounded-lg border border-pink-500/20 bg-pink-500/[0.08] p-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-pink-400">月度用量</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onForceRefreshApify}
                    className="rounded px-1.5 py-0.5 text-[10px] text-text-muted hover:bg-white/5 hover:text-text"
                  >
                    ↻ 刷新
                  </button>
                  {apifyUsage.plan_credits_usd != null && !apifyUsage.error && (
                    <span className="font-mono text-[11px] font-semibold text-text">
                      ${(apifyUsage.usage_usd ?? 0).toFixed(2)} / $
                      {(apifyUsage.plan_credits_usd ?? 0).toFixed(2)}
                      {apifyUsage.plan_name ? `  (${apifyUsage.plan_name})` : ""}
                    </span>
                  )}
                </div>
              </div>
              {apifyUsage.plan_credits_usd != null && !apifyUsage.error && (
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full transition-all"
                    style={{
                      width: `${Math.min(
                        100,
                        ((apifyUsage.usage_usd ?? 0) /
                          (apifyUsage.plan_credits_usd ?? 1)) *
                          100
                      )}%`,
                      backgroundColor:
                        (apifyUsage.usage_usd ?? 0) /
                          (apifyUsage.plan_credits_usd ?? 1) >
                        0.8
                          ? "#ef4444"
                          : "#ec4899",
                    }}
                  />
                </div>
              )}
              {apifyUsage.plan_credits_usd == null && !apifyUsage.error && (
                <p className="mt-1 text-[10px] text-text-dim">加载中...</p>
              )}
              {apifyUsage.error && (
                <p className="mt-1 text-[10px] text-danger">
                  用量查询失败：{apifyUsage.error}
                </p>
              )}
              <p className="mt-1 text-[9px] text-text-dim">
                国内代理可能需要科学上网
                {apifyUsage.usage_updated
                  ? `  ·  更新于 ${apifyUsage.usage_updated}`
                  : ""}
              </p>
            </div>
          )}
            </>
          )}
        </SettingsCard>

        {/* ---------- Telegram ---------- */}
        <SettingsCard
          icon="✈"
          iconColor="text-cyan-400"
          title="Telegram Bot"
          desc="Bot Token + 本地 API Server"
        >
          <Row label="启用">
            <Switch
              checked={config.telegram_enabled === true}
              onChange={(v) => saveConfig("telegram_enabled", v)}
            />
            <span
              className={`ml-2 rounded border px-2 py-0.5 text-[10px] font-medium ${
                config.telegram_enabled
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-white/10 bg-white/5 text-text-muted"
              }`}
            >
              {config.telegram_enabled ? "运行中" : "已停止"}
            </span>
          </Row>
          <p className="text-[10px] text-text-dim">
            启用后启动 Bot 轮询服务，接收用户发送的链接/媒体写入 Inbox
          </p>

          {/* —— 折叠区：仅在启用时展开 —— */}
          {config.telegram_enabled && (
            <>
              <Row label="Bot Token">
                <input
                  id="tg-token-input"
                  type="password"
                  placeholder="123456:ABC-DEF..."
                  defaultValue={
                    config.telegram_bot_token === "***configured***"
                      ? "••••••••••••••••"
                      : config.telegram_bot_token || ""
                  }
                  className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
                />
                <button
                  onClick={onValidateTelegram}
                  disabled={tgValidating}
                  className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-medium text-text hover:bg-white/15 disabled:opacity-40"
                >
                  {tgValidating ? "验证中..." : "验证"}
                </button>
              </Row>

              {tgValidateMsg && (
                <p
                  className={`text-xs ${
                    tgValidateMsg.startsWith("✅") ? "text-success" : "text-danger"
                  }`}
                >
                  {tgValidateMsg}
                </p>
              )}

              <Row label="API 地址">
                <input
                  type="text"
                  placeholder="https://api.telegram.org"
                  defaultValue={config.telegram_api_base || ""}
                  onBlur={(e) => saveConfig("telegram_api_base", e.target.value)}
                  className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
                />
              </Row>
              <p className="text-[10px] text-text-dim">
                自建本地 Bot API Server 可突破 20MB 下载限制（用 --local 标志启动）
              </p>

              {/* 配对码区域 */}
              {!tgState?.bound_device && (
                <Row label="配对码">
                  <span className="flex-1 font-mono text-lg font-bold text-accent">
                    {tgState?.pair_code || "—"}
                  </span>
                  {tgState?.pair_code && (
                    <button
                      onClick={onCopyPairCode}
                      className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-white/5 hover:text-text"
                    >
                      📋 复制
                    </button>
                  )}
                  <button
                    onClick={onRegenPairCode}
                    className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-white/5 hover:text-text"
                  >
                    ↻ 重新生成
                  </button>
                </Row>
              )}
              {!tgState?.bound_device && tgState?.pair_code && (
                <p className="text-[10px] text-text-dim">
                  在 Telegram 中给 @YourBot 发送此配对码即可绑定设备
                </p>
              )}

              {/* 已绑定设备区域 */}
              {tgState?.bound_device && (
                <Row label="已绑定">
                  <span className="flex-1 font-semibold text-success">
                    @{tgState.bound_device.username ||
                      tgState.bound_device.first_name ||
                      tgState.bound_device.telegram_user_id}
                  </span>
                  <button
                    onClick={() => setConfirmTgUnlink(true)}
                    className="rounded-lg bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger/20"
                  >
                    解除绑定
                  </button>
                </Row>
              )}
            </>
          )}
        </SettingsCard>

        {/* ============================================================ */}
        {/* 分组：下载 */}
        {/* ============================================================ */}
        <SectionLabel>下载</SectionLabel>

        {/* ---------- 下载设置 ---------- */}
        <SettingsCard
          icon="↓"
          iconColor="text-accent"
          title="下载设置"
          desc="下载目录、存储模式、并发与冲突策略"
        >
          <Row label="下载目录">
            <span className="flex-1 truncate font-mono text-[11px] text-text-dim">
              {(config.download_dir as string) || "—"}
            </span>
            <button
              onClick={onBrowseDownloadDir}
              className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-white/5 hover:text-text"
            >
              📁 浏览
            </button>
          </Row>

          <Row label="存储模式">
            <Select
              value={(config.storage_mode as string) || "simple"}
              options={STORAGE_MODES}
              onChange={(v) => saveConfig("storage_mode", v)}
            />
          </Row>

          <Row label="文件冲突">
            <Select
              value={(config.file_conflict_policy as string) || "rename"}
              options={CONFLICT_POLICIES}
              onChange={(v) => saveConfig("file_conflict_policy", v)}
            />
          </Row>

          <Row label="最大并发">
            <SpinBox
              min={1}
              max={10}
              value={(config.max_concurrent as number) || 3}
              onChange={(v) => saveConfig("max_concurrent", v)}
            />
          </Row>

          <Row label="最大重试">
            <SpinBox
              min={0}
              max={10}
              value={(config.max_retries as number) || 3}
              onChange={(v) => saveConfig("max_retries", v)}
            />
          </Row>
        </SettingsCard>

        {/* ---------- 缓存管理 ---------- */}
        <SettingsCard
          icon="💾"
          iconColor="text-success"
          title="缓存管理"
          desc={`总大小: ${formatSize(totalCacheSize)}${
            cacheRootPath ? `  ·  ${cacheRootPath}` : ""
          }`}
        >
          <div className="flex justify-end gap-2">
            <button
              onClick={onCleanByRules}
              className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-medium text-text hover:bg-white/15"
            >
              ↻ 立即清理
            </button>
            <button
              onClick={() => setConfirmForceClear(true)}
              className="rounded-lg bg-danger/10 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/20"
            >
              🗑 强制清空
            </button>
          </div>

          {/* 4 个缓存目录统计 */}
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Inbox Media", key: "inbox_media" },
              { label: "Thumbnails", key: "thumbs" },
              { label: "Provider Cache", key: "provider_cache" },
              { label: "Preview", key: "preview" },
            ].map((c) => {
              const s = (cacheStats as any)?.[c.key] as
                | { size_bytes?: number; file_count?: number; path?: string }
                | undefined;
              return (
                <div
                  key={c.key}
                  className="rounded-lg border border-white/10 bg-black/20 p-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] text-text-muted">{c.label}</div>
                      <div className="truncate font-mono text-[9px] text-text-dim">
                        {s?.path || ""}
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="font-mono text-xs font-bold text-text">
                        {formatSize(s?.size_bytes || 0)}
                      </div>
                      <div className="font-mono text-[9px] text-text-dim">
                        {s?.file_count || 0} 文件
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <Row label="自动清理">
            <Select
              value={(cacheMgmt.auto_clean as string) || "off"}
              options={AUTO_CLEAN_MODES}
              onChange={(v) => saveNestedConfig("cache_management", { auto_clean: v })}
            />
          </Row>

          <Row label="保留天数">
            <SpinBox
              min={1}
              max={365}
              value={(cacheMgmt.retain_days as number) || 7}
              onChange={(v) => saveNestedConfig("cache_management", { retain_days: v })}
            />
          </Row>

          <Row label="单目录上限 (MB)">
            <SpinBox
              min={50}
              max={10000}
              step={50}
              value={(cacheMgmt.max_size_mb as number) || 500}
              onChange={(v) => saveNestedConfig("cache_management", { max_size_mb: v })}
            />
          </Row>

          <Row label="上次清理">
            <span className="font-mono text-[11px] text-text-dim">
              {(cacheMgmt.last_cleaned as string)?.replace("T", " ").substring(0, 19) ||
                "从未"}
            </span>
          </Row>
        </SettingsCard>

        {/* ============================================================ */}
        {/* 分组：系统 */}
        {/* ============================================================ */}
        <SectionLabel>系统</SectionLabel>

        {/* ---------- 通用 ---------- */}
        <SettingsCard
          icon="⚙"
          iconColor="text-purple-400"
          title="通用"
          desc="语言、主题、自动下载、X-Sou 搜索"
        >
          <Row label="语言">
            <Select
              value={(config.lang as string) || "zh"}
              options={LANGS}
              onChange={(v) => onSetLang(v)}
            />
          </Row>

          <Row label="主题">
            <Select
              value={(config.theme as string) || "dark"}
              options={THEMES}
              onChange={(v) => onSetTheme(v)}
            />
          </Row>

          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="text-[13px] text-text-muted">自动下载 Inbox</div>
              <p className="text-[10px] text-text-dim">
                新内容到达 Inbox 时自动入队下载
              </p>
            </div>
            <Switch
              checked={config.auto_download_inbox === true}
              onChange={(v) => saveConfig("auto_download_inbox", v)}
            />
          </div>

          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="text-[13px] text-text-muted">启用 X-Sou 搜索</div>
              <p className="text-[10px] text-text-dim">
                Home 页面显示搜索按钮（含 18+ 内容警告）
              </p>
              {config.enable_xsou !== true && (
                <div className="mt-1 inline-block rounded-full border border-orange-400/30 bg-orange-400/10 px-2 py-0.5 text-[9px] font-medium text-orange-400">
                  ⚠ 含 18+ 内容
                </div>
              )}
            </div>
            <Switch
              checked={config.enable_xsou === true}
              onChange={(v) => saveConfig("enable_xsou", v)}
            />
          </div>
        </SettingsCard>

        {/* ---------- 关于 ---------- */}
        <SettingsCard icon="ℹ" iconColor="text-info" title="关于" desc="Lumio © 2026">
          <Row label="版本">
            <span className="font-mono text-sm font-bold text-text">
              v{(config.version as string) || "4.2"}
            </span>
            <div className="flex-1" />
            <button
              onClick={onCheckUpdate}
              className="rounded-lg bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25"
            >
              ↻ 检查更新
            </button>
          </Row>

          {updateStatus && (
            <p className="text-xs text-accent">{updateStatus}</p>
          )}

          <p className="text-center font-mono text-[10px] text-text-dim">
            Lumio © 2026 · Build {(config.build_date as string) || "2026.07.25"}
          </p>
        </SettingsCard>
      </div>

      {/* ============================================================ */}
      {/* 对话框 */}
      {/* ============================================================ */}
      {confirmCookieClear && (
        <ModalDialog title="清除 Cookie" onClose={() => setConfirmCookieClear(false)}>
          <p className="text-sm text-text">
            确定清除所有 cookie？所有平台凭证将被删除，需要重新导入。
          </p>
          <DialogActions
            onCancel={() => setConfirmCookieClear(false)}
            onConfirm={onClearCookie}
            confirmText="清除"
            danger
          />
        </ModalDialog>
      )}

      {confirmForceClear && (
        <ModalDialog title="强制清空缓存" onClose={() => setConfirmForceClear(false)}>
          <p className="text-sm text-text">
            确定强制清空全部缓存？所有 4 个缓存目录下的文件都将被删除（仅保留最近 1 天）。
          </p>
          <DialogActions
            onCancel={() => setConfirmForceClear(false)}
            onConfirm={onForceClear}
            confirmText="强制清空"
            danger
          />
        </ModalDialog>
      )}

      {confirmTgUnlink && (
        <ModalDialog title="解除 Telegram 绑定" onClose={() => setConfirmTgUnlink(false)}>
          <p className="text-sm text-text">
            确定解除 Telegram 设备绑定？解除后需重新生成配对码并重新绑定。
          </p>
          <DialogActions
            onCancel={() => setConfirmTgUnlink(false)}
            onConfirm={onUnlinkTelegram}
            confirmText="解除绑定"
            danger
          />
        </ModalDialog>
      )}
    </div>
  );
}

// ============================================================
// 子组件
// ============================================================

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-1 pt-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
      {children}
    </div>
  );
}

interface SettingsCardProps {
  icon: string;
  iconColor: string;
  title: string;
  desc?: string;
  children: React.ReactNode;
}

function SettingsCard({ icon, iconColor, title, desc, children }: SettingsCardProps) {
  return (
    <div className="glass-card flex flex-col gap-3 p-5">
      <div className="flex items-center gap-3">
        <span className={`text-xl ${iconColor}`}>{icon}</span>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-text">{title}</h3>
          {desc && <p className="mt-0.5 text-[11px] text-text-muted">{desc}</p>}
        </div>
      </div>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-24 shrink-0 text-[12px] text-text-muted">{label}</span>
      <div className="flex flex-1 items-center gap-2">{children}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "valid"
      ? "border-success/30 bg-success/10 text-success"
      : status === "warning"
      ? "border-warning/30 bg-warning/10 text-warning"
      : status === "expired"
      ? "border-danger/30 bg-danger/10 text-danger"
      : "border-white/10 bg-white/5 text-text-muted";
  const label =
    status === "valid"
      ? "正常"
      : status === "warning"
      ? "警告"
      : status === "expired"
      ? "已过期"
      : "未导入";
  return <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>;
}

function Switch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ${
        checked ? "bg-accent" : "bg-white/15"
      } ${disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer"}`}
      aria-pressed={checked}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-all duration-200 ${
          checked ? "left-[22px]" : "left-0.5"
        }`}
      />
    </button>
  );
}

function Select({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="flex-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-sm text-text focus:border-accent/50 focus:outline-none"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-zinc-900">
          {o.label}
        </option>
      ))}
    </select>
  );
}

function SpinBox({
  min,
  max,
  step = 1,
  value,
  onChange,
}: {
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex w-32 items-center gap-1 rounded-lg border border-white/10 bg-white/5">
      <button
        onClick={() => onChange(Math.max(min, value - step))}
        disabled={value <= min}
        className="px-2 py-1 text-text-muted hover:text-text disabled:opacity-30"
      >
        −
      </button>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => {
          const v = parseInt(e.target.value, 10);
          if (!isNaN(v) && v >= min && v <= max) onChange(v);
        }}
        className="w-full bg-transparent text-center text-sm text-text focus:outline-none"
      />
      <button
        onClick={() => onChange(Math.min(max, value + step))}
        disabled={value >= max}
        className="px-2 py-1 text-text-muted hover:text-text disabled:opacity-30"
      >
        +
      </button>
    </div>
  );
}

function ModalDialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="glass-card w-[420px] max-w-[90vw] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-base font-semibold text-text">{title}</h2>
        {children}
      </div>
    </div>
  );
}

function DialogActions({
  onCancel,
  onConfirm,
  confirmText,
  danger,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  confirmText: string;
  danger?: boolean;
}) {
  return (
    <div className="mt-5 flex justify-end gap-2">
      <button
        onClick={onCancel}
        className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
      >
        取消
      </button>
      <button
        onClick={onConfirm}
        className={`rounded-lg px-4 py-1.5 text-sm font-medium text-white transition-colors ${
          danger ? "bg-danger hover:bg-danger-glow" : "bg-accent hover:opacity-90"
        }`}
      >
        {confirmText}
      </button>
    </div>
  );
}

// ============================================================
// 工具函数
// ============================================================

function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}
