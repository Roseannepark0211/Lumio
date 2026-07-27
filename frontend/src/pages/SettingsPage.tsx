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

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
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
import { useI18n } from "../i18n";
import { useTheme } from "../theme";

// ============================================================
// 常量
// ============================================================

// 8 个平台 cookie 状态展示（label 通过 tr(labelKey) 渲染）
const PLATFORM_COOKIE_KEYS: { key: string; labelKey: string }[] = [
  { key: "instagram", labelKey: "cookie_status_ig" },
  { key: "x", labelKey: "cookie_status_x" },
  { key: "youtube", labelKey: "cookie_status_yt" },
  { key: "weibo", labelKey: "cookie_status_wb" },
  { key: "douyin", labelKey: "cookie_status_dy" },
  { key: "xiaohongshu", labelKey: "cookie_status_xhs" },
  { key: "bilibili", labelKey: "cookie_status_bili" },
  { key: "kuaishou", labelKey: "cookie_status_ks" },
];

// 存储模式（labelKey → tr() 渲染）
const STORAGE_MODE_VALUES = [
  { value: "simple", labelKey: "storage_simple" },
  { value: "organized", labelKey: "storage_organized" },
];

// 文件冲突策略
const CONFLICT_POLICY_VALUES = [
  { value: "rename", labelKey: "conflict_rename" },
  { value: "skip", labelKey: "conflict_skip" },
  { value: "overwrite", labelKey: "conflict_overwrite" },
  { value: "ask", labelKey: "conflict_ask" },
];

// 自动清理模式
const AUTO_CLEAN_MODE_VALUES = [
  { value: "off", labelKey: "auto_clean_off" },
  { value: "startup", labelKey: "auto_clean_startup" },
  { value: "daily", labelKey: "auto_clean_daily" },
  { value: "weekly", labelKey: "auto_clean_weekly" },
];

const LANG_VALUES = [
  { value: "zh", labelKey: "language_zh" },
  { value: "en", labelKey: "language_en" },
];

const THEME_VALUES = [
  { value: "dark", labelKey: "theme_dark" },
  { value: "light", labelKey: "theme_light" },
];

const COOKIE_FILTER = [{ name: "Cookie Files", extensions: ["txt"] }];

// ============================================================
// 主组件
// ============================================================

export function SettingsPage() {
  // —— i18n ——
  const { tr, lang, setLang: setI18nLang } = useI18n();
  // —— 主题 ——
  const { theme, setTheme: setThemeState } = useTheme();

  // —— 派生：i18n 选项（tr 变化时重新生成） ——
  const storageModes = useMemo(
    () => STORAGE_MODE_VALUES.map((m) => ({ value: m.value, label: tr(m.labelKey) })),
    [tr]
  );
  const conflictPolicies = useMemo(
    () => CONFLICT_POLICY_VALUES.map((m) => ({ value: m.value, label: tr(m.labelKey) })),
    [tr]
  );
  const autoCleanModes = useMemo(
    () => AUTO_CLEAN_MODE_VALUES.map((m) => ({ value: m.value, label: tr(m.labelKey) })),
    [tr]
  );
  const langs = useMemo(
    () => LANG_VALUES.map((m) => ({ value: m.value, label: tr(m.labelKey) })),
    [tr]
  );
  const themes = useMemo(
    () => THEME_VALUES.map((m) => ({ value: m.value, label: tr(m.labelKey) })),
    [tr]
  );

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
        showToast(tr("cookie_cleared"));
        const cs = await api.getCookieStatus();
        setCookieStatus(cs);
      } else {
        showToast(r.error || "清除失败");
      }
    } catch (e) {
      showToast(`清除失败: ${e}`);
    }
  }, [showToast, tr]);

  // —— Telegram 操作 ——
  const onValidateTelegram = useCallback(async () => {
    if (tgValidating) return;
    const tokenInput = (document.getElementById("tg-token-input") as HTMLInputElement)?.value || "";
    // config.telegram_bot_token 在后端被脱敏为 "***configured***"，不能用作真实 token。
    // 用户必须输入新 token 才能验证（占位符 ••• 或空都视为未输入）。
    const token = tokenInput === "••••••••••••••••" ? "" : tokenInput.trim();
    if (!token) {
      setTgValidateMsg(tr("telegram_token_empty"));
      return;
    }
    setTgValidating(true);
    setTgValidateMsg(tr("telegram_validating"));
    try {
      const r = await api.validateTelegram(token, config.http_proxy || "");
      if (r.ok) {
        setTgValidateMsg(tr("telegram_validate_ok", { username: r.username || "" }));
        // 验证成功才保存 token（失败不保存，避免覆盖旧的有效 token）
        await saveConfig("telegram_bot_token", token);
        // 重新生成配对码
        await api.getTelegramPairCode();
        const ts = await api.getTelegramState();
        setTgState(ts);
      } else {
        setTgValidateMsg(`❌ ${tr("telegram_validate_fail")}：${r.error || ""}`);
      }
    } catch (e) {
      setTgValidateMsg(`❌ ${tr("telegram_validate_fail")}：${e}`);
    } finally {
      setTgValidating(false);
    }
  }, [tgValidating, config.http_proxy, saveConfig, tr]);

  const onCopyPairCode = useCallback(async () => {
    const code = tgState?.pair_code || "";
    if (!code) return;
    try {
      await api.copyToClipboard(code);
      showToast(tr("telegram_copied"));
    } catch (e) {
      console.warn("copy failed:", e);
    }
  }, [tgState, showToast, tr]);

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
        showToast(tr("telegram_unlinked"));
        const ts = await api.getTelegramState();
        setTgState(ts);
      } else {
        showToast(r.error || "解绑失败");
      }
    } catch (e) {
      showToast(`解绑失败: ${e}`);
    }
  }, [showToast, tr]);

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
      setApifyValidateMsg(tr("apify_token_empty"));
      return;
    }
    if (!actor) {
      setApifyValidateMsg(tr("apify_actor_empty"));
      return;
    }
    setApifyValidating(true);
    setApifyValidateMsg(tr("apify_validating"));
    try {
      const r = await api.validateApify(token, actor);
      if (r.ok) {
        setApifyValidateMsg(`✅ ${tr("apify_connected")}`);
        const as = await api.getApifyStatus();
        setApifyState(as);
        // 强制刷新用量
        api.forceRefreshApifyUsage().catch(() => {});
      } else {
        setApifyValidateMsg(`❌ ${r.error || tr("apify_validate_fail")}`);
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
  }, [apifyValidating, config.apify_ig_actor, showToast, tr]);

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
    setUpdateStatus(tr("settings_update_checking"));
    try {
      const r: CheckUpdateResult = await api.checkUpdate();
      if (r.error) {
        setUpdateStatus(`❌ ${tr("settings_update_error", { err: r.error })}`);
      } else if (r.has_update) {
        setUpdateStatus(`🆕 ${tr("settings_update_found", { ver: `v${r.latest}` })}（当前 v${r.current}）`);
      } else {
        setUpdateStatus(`✅ ${tr("settings_update_latest")} v${r.current}`);
      }
    } catch (e) {
      setUpdateStatus(`❌ ${tr("settings_update_error", { err: String(e) })}`);
    }
  }, [tr]);

  // —— 主题 / 语言切换 ——
  const onSetTheme = useCallback(
    async (next: string) => {
      try {
        // 调 ThemeProvider.setTheme（乐观更新 + api.setTheme + WS 事件）
        await setThemeState(next === "dark" ? "dark" : "light");
      } catch (e) {
        showToast(`主题切换失败: ${e}`);
      }
    },
    [showToast, setThemeState]
  );

  const onSetLang = useCallback(
    async (next: string) => {
      try {
        // 调后端 setLang → 后端发 lang_changed 事件 → I18nProvider 自动更新 lang
        // 这里同时调 i18n 的 setLang（语义相同，保留以防 WS 事件丢失）
        await api.setLang(next);
        await setI18nLang(next as "zh" | "en");
      } catch (e) {
        showToast(`语言切换失败: ${e}`);
      }
    },
    [showToast, setI18nLang]
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
          <h1 className="text-xl font-bold text-text">{tr("settings")}</h1>
          <p className="mt-0.5 text-xs text-text-muted">
            {tr("settings_subtitle")}
          </p>
        </header>

        {/* ============================================================ */}
        {/* 分组：账号 */}
        {/* ============================================================ */}
        <SectionLabel>{tr("settings_group_account")}</SectionLabel>

        {/* ---------- Cookie 管理 ---------- */}
        <SettingsCard
          icon="🍪"
          iconColor="text-warning"
          title={tr("cookie_mgmt")}
          desc="IG / X / 微博等平台访问凭证"
        >
          <Row label={tr("cookie_status")}>
            <StatusBadge status={cookieStatus?.overall || "missing"} />
            <div className="flex-1" />
            <button
              onClick={() => setConfirmCookieClear(true)}
              className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-text/[0.06] hover:text-text"
            >
              🗑 {tr("cookie_clear_btn")}
            </button>
            <button
              onClick={onImportCookie}
              className="rounded-lg bg-accent/15 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/25"
            >
              ↓ {tr("cookie_import_btn")}
            </button>
          </Row>

          {/* Cookie 文件路径 */}
          <div className="truncate font-mono text-[10px] text-text-dim">
            {(config.cookie_file as string) || "—"}
          </div>

          {/* 各平台单独状态 */}
          <div className="mt-2 text-[10px] uppercase tracking-wider text-text-muted">
            {tr("cookie_per_platform")}
          </div>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
            {PLATFORM_COOKIE_KEYS.map((p) => {
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
                  className="flex items-center gap-2 rounded-md border border-text/15 bg-text/[0.06] px-2 py-1.5"
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
                  <span className="flex-1 text-[11px] text-text">{tr(p.labelKey)}</span>
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
          title={tr("settings_apify_section")}
          desc={tr("apify_section_desc")}
        >
          <Row label={tr("apify_enable")}>
            <Switch
              checked={config.instagram_mode === "api"}
              onChange={(v) => saveConfig("instagram_mode", v ? "api" : "cookie")}
            />
            <span
              className={`ml-2 rounded border px-2 py-0.5 text-[10px] font-medium ${
                config.instagram_mode === "api"
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-text/15 bg-text/[0.06] text-text-muted"
              }`}
            >
              {config.instagram_mode === "api" ? tr("apify_status_on") : tr("apify_status_off")}
            </span>
          </Row>
          <p className="text-[10px] text-text-dim">
            {tr("apify_enable_hint")}
          </p>

          {/* —— 折叠区：仅在启用时展开 —— */}
          {config.instagram_mode === "api" && (
            <>
              <Row label={tr("apify_token")}>
                <input
                  id="apify-token-input"
                  type="password"
                  placeholder="apify_api_..."
                  defaultValue={
                    apifyState?.token_configured ? "••••••••••••••••" : ""
                  }
                  className="flex-1 rounded-lg border border-text/15 bg-text/[0.06] px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
                />
                <button
                  onClick={onValidateApify}
                  disabled={apifyValidating}
                  className="rounded-lg bg-text/10 px-3 py-1.5 text-xs font-medium text-text hover:bg-white/15 disabled:opacity-40"
                >
                  {apifyValidating ? tr("apify_validating") : tr("apify_validate")}
                </button>
              </Row>

              <Row label={tr("apify_actor_id")}>
                <input
                  id="apify-actor-input"
                  type="text"
                  placeholder="shu8hvrXbJbY3Eb9W"
                  defaultValue={apifyState?.actor_id || ""}
                  onBlur={(e) => {
                    const v = e.target.value;
                    if (v) saveConfig("apify_ig_actor", v);
                  }}
                  className="flex-1 rounded-lg border border-text/15 bg-text/[0.06] px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
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
                    ● {apifyState.connected ? tr("apify_connected") : tr("apify_pending_verify")}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full border border-text/15 bg-text/[0.06] px-2 py-0.5 text-[10px] font-medium text-text-muted">
                    ● 未配置
                  </span>
                )}
              </div>

              {/* 月度用量条 */}
              {apifyState?.connected && (
            <div className="rounded-lg border border-pink-500/20 bg-pink-500/[0.08] p-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-pink-400">{tr("apify_quota_label")}</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onForceRefreshApify}
                    className="rounded px-1.5 py-0.5 text-[10px] text-text-muted hover:bg-text/[0.06] hover:text-text"
                  >
                    ↻ {tr("apify_quota_refresh")}
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
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-text/10">
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
                <p className="mt-1 text-[10px] text-text-dim">{tr("apify_quota_loading")}</p>
              )}
              {apifyUsage.error && (
                <p className="mt-1 text-[10px] text-danger">
                  {tr("apify_quota_error", { err: apifyUsage.error })}
                </p>
              )}
              <p className="mt-1 text-[9px] text-text-dim">
                {tr("apify_proxy_hint")}
                {apifyUsage.usage_updated
                  ? `  ·  ${tr("apify_quota_updated")} ${apifyUsage.usage_updated}`
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
          title={tr("telegram_settings")}
          desc="Bot Token + 本地 API Server"
        >
          <Row label={tr("telegram_enable")}>
            <Switch
              checked={config.telegram_enabled === true}
              onChange={(v) => saveConfig("telegram_enabled", v)}
            />
            <span
              className={`ml-2 rounded border px-2 py-0.5 text-[10px] font-medium ${
                config.telegram_enabled
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-text/15 bg-text/[0.06] text-text-muted"
              }`}
            >
              {config.telegram_enabled ? "运行中" : "已停止"}
            </span>
          </Row>
          <p className="text-[10px] text-text-dim">
            {tr("telegram_enable_hint")}
          </p>

          {/* —— 折叠区：仅在启用时展开 —— */}
          {config.telegram_enabled && (
            <>
              <Row label={tr("bot_token")}>
                <input
                  id="tg-token-input"
                  type="password"
                  placeholder="123456:ABC-DEF..."
                  defaultValue={
                    config.telegram_bot_token === "***configured***"
                      ? "••••••••••••••••"
                      : config.telegram_bot_token || ""
                  }
                  className="flex-1 rounded-lg border border-text/15 bg-text/[0.06] px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
                />
                <button
                  onClick={onValidateTelegram}
                  disabled={tgValidating}
                  className="rounded-lg bg-text/10 px-3 py-1.5 text-xs font-medium text-text hover:bg-white/15 disabled:opacity-40"
                >
                  {tgValidating ? tr("telegram_validating") : tr("telegram_validate_btn")}
                </button>
              </Row>

              {tgValidateMsg && (
                <p
                  className={`text-xs ${
                    tgValidateMsg.startsWith("✅") || tgValidateMsg.startsWith("🟢") ? "text-success" : "text-danger"
                  }`}
                >
                  {tgValidateMsg}
                </p>
              )}

              <Row label={tr("api_address")}>
                <input
                  type="text"
                  placeholder="https://api.telegram.org"
                  defaultValue={config.telegram_api_base || ""}
                  onBlur={(e) => saveConfig("telegram_api_base", e.target.value)}
                  className="flex-1 rounded-lg border border-text/15 bg-text/[0.06] px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
                />
              </Row>
              <p className="text-[10px] text-text-dim">
                自建本地 Bot API Server 可突破 20MB 下载限制（用 --local 标志启动）
              </p>

              {/* 配对码区域 */}
              {!tgState?.bound_device && (
                <Row label={tr("telegram_pair_code_label")}>
                  <span className="flex-1 font-mono text-lg font-bold text-accent">
                    {tgState?.pair_code || "—"}
                  </span>
                  {tgState?.pair_code && (
                    <button
                      onClick={onCopyPairCode}
                      className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-text/[0.06] hover:text-text"
                    >
                      📋 {tr("telegram_copy_btn")}
                    </button>
                  )}
                  <button
                    onClick={onRegenPairCode}
                    className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-text/[0.06] hover:text-text"
                  >
                    ↻ {tr("telegram_regen_btn")}
                  </button>
                </Row>
              )}
              {!tgState?.bound_device && tgState?.pair_code && (
                <p className="text-[10px] text-text-dim">
                  {tr("telegram_pair_hint")}
                </p>
              )}

              {/* 已绑定设备区域 */}
              {tgState?.bound_device && (
                <Row label={tr("telegram_bound_label")}>
                  <span className="flex-1 font-semibold text-success">
                    @{tgState.bound_device.username ||
                      tgState.bound_device.first_name ||
                      tgState.bound_device.telegram_user_id}
                  </span>
                  <button
                    onClick={() => setConfirmTgUnlink(true)}
                    className="rounded-lg bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger/20"
                  >
                    {tr("telegram_unlink_btn")}
                  </button>
                </Row>
              )}
            </>
          )}
        </SettingsCard>

        {/* ============================================================ */}
        {/* 分组：下载 */}
        {/* ============================================================ */}
        <SectionLabel>{tr("download_settings")}</SectionLabel>

        {/* ---------- 下载设置 ---------- */}
        <SettingsCard
          icon="↓"
          iconColor="text-accent"
          title={tr("settings_download_section")}
          desc="下载目录、存储模式、并发与冲突策略"
        >
          <Row label={tr("download_dir")}>
            <span className="flex-1 truncate font-mono text-[11px] text-text-dim">
              {(config.download_dir as string) || "—"}
            </span>
            <button
              onClick={onBrowseDownloadDir}
              className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-text/[0.06] hover:text-text"
            >
              📁 {tr("browse")}
            </button>
          </Row>

          <Row label={tr("storage_mode")}>
            <Select
              value={(config.storage_mode as string) || "simple"}
              options={storageModes}
              onChange={(v) => saveConfig("storage_mode", v)}
            />
          </Row>

          <Row label={tr("file_conflict")}>
            <Select
              value={(config.file_conflict_policy as string) || "rename"}
              options={conflictPolicies}
              onChange={(v) => saveConfig("file_conflict_policy", v)}
            />
          </Row>

          <Row label={tr("max_concurrent")}>
            <SpinBox
              min={1}
              max={10}
              value={(config.max_concurrent as number) || 3}
              onChange={(v) => saveConfig("max_concurrent", v)}
            />
          </Row>

          <Row label={tr("max_retries")}>
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
          title={tr("settings_cache")}
          desc={`总大小: ${formatSize(totalCacheSize)}${
            cacheRootPath ? `  ·  ${cacheRootPath}` : ""
          }`}
        >
          <div className="flex justify-end gap-2">
            <button
              onClick={onCleanByRules}
              className="rounded-lg bg-text/10 px-3 py-1.5 text-xs font-medium text-text hover:bg-white/15"
            >
              ↻ {tr("clean_now")}
            </button>
            <button
              onClick={() => setConfirmForceClear(true)}
              className="rounded-lg bg-danger/10 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/20"
            >
              🗑 {tr("force_clear_all")}
            </button>
          </div>

          {/* 4 个缓存目录统计 */}
          <div className="grid grid-cols-2 gap-2">
            {[
              { labelKey: "cache_inbox", key: "inbox_media" },
              { labelKey: "cache_thumbs", key: "thumbs" },
              { labelKey: "cache_provider", key: "provider_cache" },
              { labelKey: "cache_preview", key: "preview" },
            ].map((c) => {
              const s = (cacheStats as any)?.[c.key] as
                | { size_bytes?: number; file_count?: number; path?: string }
                | undefined;
              return (
                <div
                  key={c.key}
                  className="rounded-lg border border-white/10 bg-text/[0.08] p-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] text-text-muted">{tr(c.labelKey)}</div>
                      <div className="truncate font-mono text-[9px] text-text-dim">
                        {s?.path || ""}
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="font-mono text-xs font-bold text-text">
                        {formatSize(s?.size_bytes || 0)}
                      </div>
                      <div className="font-mono text-[9px] text-text-dim">
                        {s?.file_count || 0} {tr("cache_files")}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <Row label={tr("auto_clean")}>
            <Select
              value={(cacheMgmt.auto_clean as string) || "off"}
              options={autoCleanModes}
              onChange={(v) => saveNestedConfig("cache_management", { auto_clean: v })}
            />
          </Row>

          <Row label={tr("retain_days")}>
            <SpinBox
              min={1}
              max={365}
              value={(cacheMgmt.retain_days as number) || 7}
              onChange={(v) => saveNestedConfig("cache_management", { retain_days: v })}
            />
          </Row>

          <Row label={tr("max_size_mb")}>
            <SpinBox
              min={50}
              max={10000}
              step={50}
              value={(cacheMgmt.max_size_mb as number) || 500}
              onChange={(v) => saveNestedConfig("cache_management", { max_size_mb: v })}
            />
          </Row>

          <Row label={tr("last_cleaned")}>
            <span className="font-mono text-[11px] text-text-dim">
              {(cacheMgmt.last_cleaned as string)?.replace("T", " ").substring(0, 19) ||
                tr("never")}
            </span>
          </Row>
        </SettingsCard>

        {/* ============================================================ */}
        {/* 分组：系统 */}
        {/* ============================================================ */}
        <SectionLabel>{tr("settings_group_system")}</SectionLabel>

        {/* ---------- 通用 ---------- */}
        <SettingsCard
          icon="⚙"
          iconColor="text-purple-400"
          title={tr("general")}
          desc="语言、主题、自动下载、X-Sou 搜索"
        >
          <Row label={tr("language")}>
            <Select
              value={lang}
              options={langs}
              onChange={(v) => onSetLang(v)}
            />
          </Row>

          <Row label={tr("theme_light") + " / " + tr("theme_dark")}>
            <Select
              value={theme}
              options={themes}
              onChange={(v) => onSetTheme(v)}
            />
          </Row>

          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="text-[13px] text-text-muted">{tr("auto_download_inbox")}</div>
              <p className="text-[10px] text-text-dim">
                {tr("auto_download_inbox_desc")}
              </p>
            </div>
            <Switch
              checked={config.auto_download_inbox === true}
              onChange={(v) => saveConfig("auto_download_inbox", v)}
            />
          </div>

          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="text-[13px] text-text-muted">{tr("enable_xsou")}</div>
              <p className="text-[10px] text-text-dim">
                {tr("enable_xsou_desc")}
              </p>
              {config.enable_xsou !== true && (
                <div className="mt-1 inline-block rounded-full border border-orange-400/30 bg-orange-400/10 px-2 py-0.5 text-[9px] font-medium text-orange-400">
                  {tr("enable_xsou_warning")}
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
        <SettingsCard icon="ℹ" iconColor="text-info" title={tr("about")} desc="Lumio © 2026">
          <Row label={tr("version")}>
            <span className="font-mono text-sm font-bold text-text">
              v{(config.version as string) || "4.2"}
            </span>
            <div className="flex-1" />
            <button
              onClick={onCheckUpdate}
              className="rounded-lg bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25"
            >
              ↻ {tr("settings_check_update")}
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
        <ModalDialog title={tr("cookie_clear_btn")} onClose={() => setConfirmCookieClear(false)}>
          <p className="text-sm text-text">
            {tr("cookie_clear_confirm")}
          </p>
          <DialogActions
            onCancel={() => setConfirmCookieClear(false)}
            onConfirm={onClearCookie}
            confirmText={tr("clear")}
            danger
          />
        </ModalDialog>
      )}

      {confirmForceClear && (
        <ModalDialog title={tr("force_clear_all")} onClose={() => setConfirmForceClear(false)}>
          <p className="text-sm text-text">
            {tr("cache_force_confirm")}
          </p>
          <DialogActions
            onCancel={() => setConfirmForceClear(false)}
            onConfirm={onForceClear}
            confirmText={tr("force_clear_all")}
            danger
          />
        </ModalDialog>
      )}

      {confirmTgUnlink && (
        <ModalDialog title={tr("telegram_unlink_btn")} onClose={() => setConfirmTgUnlink(false)}>
          <p className="text-sm text-text">
            确定解除 Telegram 设备绑定？解除后需重新生成配对码并重新绑定。
          </p>
          <DialogActions
            onCancel={() => setConfirmTgUnlink(false)}
            onConfirm={onUnlinkTelegram}
            confirmText={tr("telegram_unlink_btn")}
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
  const { tr } = useI18n();
  const cls =
    status === "valid"
      ? "border-success/30 bg-success/10 text-success"
      : status === "warning"
      ? "border-warning/30 bg-warning/10 text-warning"
      : status === "expired"
      ? "border-danger/30 bg-danger/10 text-danger"
      : "border-text/15 bg-text/[0.06] text-text-muted";
  const label =
    status === "valid"
      ? tr("cookie_status_valid")
      : status === "warning"
      ? tr("cookie_status_warning")
      : status === "expired"
      ? tr("cookie_status_expired")
      : tr("cookie_status_missing");
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
  className = "",
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`w-fit min-w-[5rem] rounded-lg border border-text/15 bg-bg-surface px-2.5 py-1.5 text-sm text-text shadow-sm transition-colors hover:border-text/25 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40 ${className}`}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-bg-surface text-text">
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
  // [−] [可编辑数字] [+] 三段式
  // - ± 按钮单击步进 step
  // - 中间 input 可键盘输入数字，失焦/回车时校验范围并提交
  // - 隐藏浏览器自带 spinner（appearance: none）
  const [text, setText] = useState(String(value));

  // 外部 value 变化时同步 text（如配置被其他地方修改）
  useEffect(() => {
    setText(String(value));
  }, [value]);

  const commit = useCallback(
    (raw: string) => {
      const v = parseInt(raw, 10);
      if (isNaN(v)) {
        setText(String(value));
        return;
      }
      const clamped = Math.max(min, Math.min(max, v));
      if (clamped !== value) {
        onChange(clamped);
      } else {
        setText(String(clamped));
      }
    },
    [min, max, onChange, value]
  );

  return (
    <div className="flex h-8 w-fit items-center overflow-hidden rounded-lg border border-text/15 bg-bg-surface shadow-sm transition-colors hover:border-text/25 focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/40">
      <button
        onClick={() => onChange(Math.max(min, value - step))}
        disabled={value <= min}
        className="btn-press flex h-8 w-8 items-center justify-center text-text-muted hover:bg-text/[0.06] hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
        title="-"
        aria-label="decrease"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <line x1="3" y1="8" x2="13" y2="8" />
        </svg>
      </button>
      <input
        type="text"
        inputMode="numeric"
        value={text}
        onChange={(e) => {
          // 只允许数字（含空字符串，便于清空后重输）
          const raw = e.target.value.replace(/[^\d]/g, "");
          setText(raw);
        }}
        onBlur={() => commit(text)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.currentTarget.blur();
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            onChange(Math.min(max, value + step));
          } else if (e.key === "ArrowDown") {
            e.preventDefault();
            onChange(Math.max(min, value - step));
          }
        }}
        className="h-8 w-12 border-x border-text/10 bg-bg-elevated/40 px-1 text-center font-mono text-[13px] font-semibold tabular-nums text-text focus:outline-none"
        aria-label="value"
      />
      <button
        onClick={() => onChange(Math.min(max, value + step))}
        disabled={value >= max}
        className="btn-press flex h-8 w-8 items-center justify-center text-text-muted hover:bg-text/[0.06] hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
        title="+"
        aria-label="increase"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <line x1="8" y1="3" x2="8" y2="13" />
          <line x1="3" y1="8" x2="13" y2="8" />
        </svg>
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
  const { tr } = useI18n();
  return (
    <div className="mt-5 flex justify-end gap-2">
      <button
        onClick={onCancel}
        className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-text/10 hover:text-text"
      >
        {tr("cancel")}
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
