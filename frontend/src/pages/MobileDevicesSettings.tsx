/**
 * 移动设备管理设置卡片（独立组件）。
 *
 * ⚠️ 仅在开发模式下渲染（由 SettingsPage 通过 `import.meta.env.DEV` 条件渲染）。
 * 构建版本（electron-builder 打包后）中此组件无任何可达引用，
 * Rollup tree-shaking 会移除整个模块，构建产物中不包含：
 *   - 移动端 API 端点字符串（/api/auth/pair-code、/api/devices 等）
 *   - 移动端相关状态逻辑、useCallback 函数体
 *   - DeviceRow 子组件、对话框
 * 从而避免逆向工程者从构建产物中探测到移动端 API 接口存在。
 *
 * 设计权衡：此文件内重复定义了 SettingsCard/Row/Switch/DialogActions 等通用 UI 组件
 * （与 SettingsPage.tsx 中的定义同名同结构）。这是有意为之 ——
 * 避免抽取共享 primitives 模块带来的过度工程化，且此文件构建时被 tree-shake，
 * 重复代码不会进入构建产物，无运行时成本。
 */

import { useEffect, useState, useCallback } from "react";
import { api } from "../api";
import {
  type Device,
  type PairCodeResponse,
  type ServerInfo,
  genPairCode,
  getServerInfo,
  listDevices,
  renameDevice,
  revokeDevice,
  purgeDevice,
  restartFastApi,
} from "../apiMobile";
import { useToast } from "../App";
import { useI18n } from "../i18n";
import { ModalDialog } from "../components/ModalDialog";

// ============================================================
// 主组件
// ============================================================

interface MobileDevicesSettingsProps {
  /** 父组件的 config state（用于读取 allow_mobile_connect） */
  config: Record<string, any>;
  /** 父组件的 saveConfig 函数（保存 allow_mobile_connect 后通知父组件刷新） */
  saveConfig: (key: string, value: unknown) => Promise<void>;
}

export function MobileDevicesSettings({ config, saveConfig }: MobileDevicesSettingsProps) {
  const { tr } = useI18n();
  const showToast = useToast();

  // —— 已连接设备（移动设备管理） ——
  const [devices, setDevices] = useState<Device[]>([]);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [devicesError, setDevicesError] = useState<string | null>(null);
  const [mobilePairCode, setMobilePairCode] = useState<{ code: string; expires_in: number } | null>(null);
  const [pairCodeLoading, setPairCodeLoading] = useState(false);
  // 配对码剩余秒数倒计时（每秒递减，0 时清除配对码）
  const [pairCountdown, setPairCountdown] = useState(0);

  // —— 移动端连接：服务信息 + FastAPI 重启 ——
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null);
  const [restartLoading, setRestartLoading] = useState(false);
  const [restartMsg, setRestartMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  // allow_mobile_connect 开关变化后需重启 FastAPI 才生效，记录"待重启"状态
  const [pendingRestart, setPendingRestart] = useState(false);
  // 重命名 / 撤销对话框目标设备
  const [renameTarget, setRenameTarget] = useState<Device | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameSubmitting, setRenameSubmitting] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<Device | null>(null);
  const [revokeSubmitting, setRevokeSubmitting] = useState(false);
  // 彻底删除已撤销设备（purge）
  const [purgeTarget, setPurgeTarget] = useState<Device | null>(null);
  const [purgeSubmitting, setPurgeSubmitting] = useState(false);

  // —— 已连接设备：拉取 ——
  const reloadDevices = useCallback(async () => {
    setDevicesLoading(true);
    setDevicesError(null);
    try {
      const list = await listDevices();
      setDevices(list || []);
    } catch (e) {
      setDevicesError(String(e));
    } finally {
      setDevicesLoading(false);
    }
  }, []);

  useEffect(() => {
    reloadDevices();
  }, [reloadDevices]);

  // —— 移动端连接：拉取服务信息 ——
  const reloadServerInfo = useCallback(async () => {
    try {
      const info = await getServerInfo();
      setServerInfo(info);
    } catch (e) {
      console.warn("getServerInfo failed:", e);
    }
  }, []);

  useEffect(() => {
    reloadServerInfo();
  }, [reloadServerInfo]);

  // —— 配对码倒计时（每秒递减） ——
  useEffect(() => {
    if (pairCountdown <= 0) return;
    const timer = setInterval(() => {
      setPairCountdown((prev) => {
        if (prev <= 1) {
          setMobilePairCode(null);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [pairCountdown]);

  // —— 允许移动端连接开关变化 ——
  const onToggleAllowMobileConnect = useCallback(
    async (v: boolean) => {
      // 先保存配置
      await saveConfig("allow_mobile_connect", v);
      // 标记"待重启"——用户需手动点"立即重启 FastAPI"按钮才生效
      setPendingRestart(true);
      // 乐观更新 serverInfo 显示
      setServerInfo((prev) =>
        prev
          ? {
              ...prev,
              allow_mobile_connect: v,
              listening_all_interfaces: v,
              host: v ? "0.0.0.0" : "127.0.0.1",
            }
          : prev
      );
    },
    [saveConfig]
  );

  // —— 重启 FastAPI（让 allow_mobile_connect 开关生效） ——
  const onRestartFastApi = useCallback(async () => {
    if (restartLoading) return;
    setRestartLoading(true);
    setRestartMsg(null);
    try {
      const r = await restartFastApi();
      if (r.ok) {
        setRestartMsg({ type: "ok", text: tr("mobile_connect_restart_ok") });
        setPendingRestart(false);
        // 重启后重新拉取服务信息（host/port 可能变化）
        await reloadServerInfo();
      } else {
        setRestartMsg({
          type: "err",
          text: tr("mobile_connect_restart_failed", { err: r.error || "" }),
        });
      }
    } catch (e: any) {
      setRestartMsg({
        type: "err",
        text: tr("mobile_connect_restart_failed", { err: e?.message || String(e) }),
      });
    } finally {
      setRestartLoading(false);
    }
  }, [restartLoading, tr, reloadServerInfo]);

  // —— 复制局域网 IP 到剪贴板 ——
  const onCopyLanIp = useCallback(
    async (ip: string) => {
      try {
        await api.copyToClipboard(ip);
        showToast(tr("mobile_connect_copy_ip") + ": " + ip);
      } catch (e) {
        console.warn("copy ip failed:", e);
      }
    },
    [showToast, tr]
  );

  const onGenPairCode = useCallback(async () => {
    if (pairCodeLoading) return;
    setPairCodeLoading(true);
    try {
      const r: PairCodeResponse = await genPairCode();
      setMobilePairCode({ code: r.pair_code, expires_in: r.expires_in });
      // 启动倒计时（r.expires_in 通常为 300 秒 = 5 分钟）
      setPairCountdown(r.expires_in);
    } catch (e) {
      showToast(`生成配对码失败: ${e}`);
    } finally {
      setPairCodeLoading(false);
    }
  }, [pairCodeLoading, showToast]);

  const onCopyMobilePairCode = useCallback(async () => {
    const code = mobilePairCode?.code || "";
    if (!code) return;
    try {
      await api.copyToClipboard(code);
      showToast(tr("telegram_copied"));
    } catch (e) {
      console.warn("copy failed:", e);
    }
  }, [mobilePairCode, showToast, tr]);

  // 打开重命名对话框时预填当前设备名
  const openRenameDialog = useCallback((device: Device) => {
    setRenameTarget(device);
    setRenameValue(device.device_name);
    setRenameSubmitting(false);
  }, []);

  const onConfirmRename = useCallback(async () => {
    if (!renameTarget) return;
    const name = renameValue.trim();
    if (!name) {
      showToast(tr("devices_rename_placeholder"));
      return;
    }
    setRenameSubmitting(true);
    try {
      const updated = await renameDevice(renameTarget.device_id, name);
      if (updated) {
        setDevices((prev) =>
          prev.map((d) => (d.device_id === renameTarget.device_id ? updated : d))
        );
        showToast(tr("devices_renamed", { name }));
        setRenameTarget(null);
      } else {
        showToast("重命名失败");
      }
    } catch (e) {
      showToast(`重命名失败: ${e}`);
    } finally {
      setRenameSubmitting(false);
    }
  }, [renameTarget, renameValue, showToast, tr]);

  const onConfirmRevoke = useCallback(async () => {
    if (!revokeTarget) return;
    const target = revokeTarget;
    setRevokeSubmitting(true);
    try {
      await revokeDevice(target.device_id);
      setDevices((prev) =>
        prev.map((d) => (d.device_id === target.device_id ? { ...d, revoked: true } : d))
      );
      showToast(tr("devices_revoked", { name: target.device_name }));
      setRevokeTarget(null);
    } catch (e) {
      showToast(`撤销失败: ${e}`);
    } finally {
      setRevokeSubmitting(false);
    }
  }, [revokeTarget, showToast, tr]);

  const onConfirmPurge = useCallback(async () => {
    if (!purgeTarget) return;
    const target = purgeTarget;
    setPurgeSubmitting(true);
    try {
      await purgeDevice(target.device_id);
      setDevices((prev) => prev.filter((d) => d.device_id !== target.device_id));
      showToast(tr("devices_purged", { name: target.device_name }));
      setPurgeTarget(null);
    } catch (e) {
      showToast(`删除失败: ${e}`);
    } finally {
      setPurgeSubmitting(false);
    }
  }, [purgeTarget, showToast, tr]);

  return (
    <>
      {/* ---------- 已连接设备（移动设备管理） ---------- */}
      <SettingsCard
        icon="📱"
        iconColor="text-emerald-400"
        title={tr("devices_section")}
        desc={tr("devices_section_desc")}
      >
        {/* —— 允许移动端连接开关 —— */}
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-[13px] text-text-muted">{tr("mobile_connect_enable")}</div>
            <p className="text-[10px] text-text-dim">
              {tr("mobile_connect_enable_hint")}
            </p>
          </div>
          <Switch
            checked={config.allow_mobile_connect === true}
            onChange={onToggleAllowMobileConnect}
          />
        </div>

        {/* 待重启提示 + 重启按钮 */}
        {pendingRestart && (
          <div className="rounded-lg border border-warning/30 bg-warning/10 p-2.5">
            <div className="flex items-center gap-2">
              <span className="flex-1 text-[11px] text-warning">
                ⚠ {tr("mobile_connect_restart_hint")}
              </span>
              <button
                onClick={onRestartFastApi}
                disabled={restartLoading}
                className="rounded-lg bg-warning/20 px-3 py-1 text-xs font-medium text-warning hover:bg-warning/30 disabled:opacity-40"
              >
                {restartLoading ? tr("mobile_connect_restarting") : tr("mobile_connect_restart_now")}
              </button>
            </div>
          </div>
        )}

        {/* 重启结果提示 */}
        {restartMsg && (
          <p className={`text-xs ${restartMsg.type === "ok" ? "text-success" : "text-danger"}`}>
            {restartMsg.type === "ok" ? "✅ " : "❌ "}{restartMsg.text}
          </p>
        )}

        {/* —— 服务信息（移动端配对需知道 IP/端口/指纹） —— */}
        {config.allow_mobile_connect === true && serverInfo && (
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.08] p-3">
            <div className="mb-2 text-[11px] font-semibold text-emerald-400">
              {tr("mobile_connect_server_info")}
            </div>

            {/* 监听状态 */}
            <div className="mb-1.5 flex items-center gap-2">
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${serverInfo.listening_all_interfaces ? "bg-success" : "bg-warning"}`} />
              <span className="text-[11px] text-text">
                {serverInfo.listening_all_interfaces
                  ? tr("mobile_connect_listening_all")
                  : tr("mobile_connect_listening_local")}
              </span>
            </div>

            {/* 局域网 IP 列表（移动端需输入此 IP） */}
            <div className="mb-1.5">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                {tr("mobile_connect_lan_ip")}
              </span>
              {serverInfo.lan_ips.length > 0 ? (
                <div className="mt-0.5 flex flex-wrap gap-1.5">
                  {serverInfo.lan_ips.map((ip) => (
                    <button
                      key={ip}
                      onClick={() => onCopyLanIp(ip)}
                      className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 font-mono text-[11px] text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/20"
                      title={tr("mobile_connect_copy_ip")}
                    >
                      {ip}
                      <span className="text-[9px] opacity-60">📋</span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="mt-0.5 text-[10px] text-text-dim">
                  {tr("mobile_connect_no_lan_ip")}
                </p>
              )}
            </div>

            {/* 端口 */}
            <div className="mb-1.5 flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                {tr("mobile_connect_port")}
              </span>
              <span className="font-mono text-[11px] text-text">{serverInfo.port}</span>
            </div>
            {/* 端口冲突警告：38910 被占用时 fallback 到 38911-38919，需提示用户在移动端手动填端口 */}
            {serverInfo.port !== 38910 && (
              <div className="mb-2 rounded-md border border-amber-500/30 bg-amber-500/[0.08] p-2">
                <p className="text-[11px] text-amber-400">
                  ⚠ 默认端口 38910 被占用，当前使用 {serverInfo.port}
                </p>
                <p className="mt-0.5 text-[10px] text-amber-400/70">
                  请在移动端配对页点击「高级」手动填写此端口
                </p>
              </div>
            )}

            {/* 证书指纹（HTTPS 模式才有，移动端校验自签证书防中间人） */}
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                {tr("mobile_connect_fingerprint")}
              </span>
              {serverInfo.cert_fingerprint ? (
                <p className="mt-0.5 break-all font-mono text-[9px] text-text-dim">
                  {serverInfo.cert_fingerprint}
                </p>
              ) : (
                <p className="mt-0.5 text-[10px] text-text-dim">
                  {tr("mobile_connect_fingerprint_empty")}
                </p>
              )}
            </div>
          </div>
        )}

        {/* 未开启移动端连接时的警告 */}
        {config.allow_mobile_connect !== true && (
          <p className="text-[10px] text-text-dim">
            ⚠ {tr("mobile_connect_off_warning")}
          </p>
        )}

        {/* 分隔线 */}
        <div className="my-1 h-px bg-text/10" />

        {/* 配对码生成（5 分钟有效，带倒计时） */}
        <Row label={tr("devices_pair_code")}>
          {mobilePairCode ? (
            <span className="flex-1 font-mono text-lg font-bold tracking-widest text-accent">
              {mobilePairCode.code}
            </span>
          ) : (
            <span className="flex-1 font-mono text-sm text-text-dim">—</span>
          )}
          {mobilePairCode && (
            <button
              onClick={onCopyMobilePairCode}
              className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-text/[0.06] hover:text-text"
            >
              📋 {tr("telegram_copy_btn")}
            </button>
          )}
          <button
            onClick={onGenPairCode}
            disabled={pairCodeLoading || config.allow_mobile_connect !== true}
            className="rounded-lg bg-accent/15 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/25 disabled:opacity-40"
            title={config.allow_mobile_connect !== true ? tr("mobile_connect_off_warning") : ""}
          >
            ↻ {mobilePairCode ? tr("devices_regenerate") : tr("devices_gen_pair_code")}
          </button>
        </Row>
        {mobilePairCode && pairCountdown > 0 && (
          <p className="text-[10px] text-text-dim">
            {tr("mobile_connect_pair_code_5min")} · ⏱ {Math.floor(pairCountdown / 60)}:{String(pairCountdown % 60).padStart(2, "0")}
          </p>
        )}

        {/* 分隔线 */}
        <div className="my-1 h-px bg-text/10" />

        {/* 设备列表 */}
        {devicesError ? (
          <p className="text-xs text-danger">{tr("devices_load_failed")}: {devicesError}</p>
        ) : devicesLoading && devices.length === 0 ? (
          <p className="text-xs text-text-muted">{tr("loading")}</p>
        ) : devices.length === 0 ? (
          <p className="text-xs text-text-dim">{tr("devices_empty")}</p>
        ) : (
          <div className="flex flex-col gap-2">
            {devices.map((d) => (
              <DeviceRow
                key={d.device_id}
                device={d}
                tr={tr}
                onRename={() => openRenameDialog(d)}
                onRevoke={() => setRevokeTarget(d)}
                onPurge={() => setPurgeTarget(d)}
              />
            ))}
          </div>
        )}

        {/* 刷新按钮 */}
        <div className="flex justify-end">
          <button
            onClick={reloadDevices}
            disabled={devicesLoading}
            className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-text/[0.06] hover:text-text disabled:opacity-40"
          >
            ↻ {tr("apify_quota_refresh")}
          </button>
        </div>
      </SettingsCard>

      {/* ============================================================ */}
      {/* 对话框 */}
      {/* ============================================================ */}

      {/* 重命名设备对话框 */}
      {renameTarget && (
        <ModalDialog
          title={tr("devices_rename_dialog_title")}
          onClose={() => setRenameTarget(null)}
        >
          <input
            type="text"
            autoFocus
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onConfirmRename();
            }}
            placeholder={tr("devices_rename_placeholder")}
            className="w-full rounded-lg border border-text/15 bg-text/[0.06] px-3 py-2 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
          />
          <DialogActions
            onCancel={() => setRenameTarget(null)}
            onConfirm={onConfirmRename}
            confirmText={tr("devices_rename")}
          />
          {renameSubmitting && (
            <p className="mt-2 text-xs text-text-muted">{tr("loading")}</p>
          )}
        </ModalDialog>
      )}

      {/* 撤销设备确认对话框 */}
      {revokeTarget && (
        <ModalDialog
          title={tr("devices_revoke_btn")}
          onClose={() => setRevokeTarget(null)}
        >
          <p className="text-sm text-text">
            {tr("devices_revoke_confirm")}
          </p>
          <p className="mt-1 text-xs text-text-muted">
            {revokeTarget.device_name} · <span className="font-mono">{revokeTarget.device_id}</span>
          </p>
          <DialogActions
            onCancel={() => setRevokeTarget(null)}
            onConfirm={onConfirmRevoke}
            confirmText={tr("devices_revoke_btn")}
            danger
          />
          {revokeSubmitting && (
            <p className="mt-2 text-xs text-text-muted">{tr("loading")}</p>
          )}
        </ModalDialog>
      )}

      {/* 彻底删除已撤销设备确认对话框 */}
      {purgeTarget && (
        <ModalDialog
          title={tr("devices_purge_btn")}
          onClose={() => setPurgeTarget(null)}
        >
          <p className="text-sm text-text">
            {tr("devices_purge_confirm")}
          </p>
          <p className="mt-1 text-xs text-text-muted">
            {purgeTarget.device_name} · <span className="font-mono">{purgeTarget.device_id}</span>
          </p>
          <DialogActions
            onCancel={() => setPurgeTarget(null)}
            onConfirm={onConfirmPurge}
            confirmText={tr("devices_purge_btn")}
            danger
          />
          {purgeSubmitting && (
            <p className="mt-2 text-xs text-text-muted">{tr("loading")}</p>
          )}
        </ModalDialog>
      )}
    </>
  );
}

// ============================================================
// 子组件（与 SettingsPage.tsx 中的定义结构一致，有意复制避免抽取共享模块）
// ============================================================

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
// 设备行（DeviceRow）— 已连接设备列表项
// ============================================================

/** 把 ISO 8601 UTC 时间格式化为本地可读字符串（YYYY-MM-DD HH:MM） */
function formatDeviceTime(iso: string, fallback = "—"): string {
  if (!iso) return fallback;
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return fallback;
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return fallback;
  }
}

interface DeviceRowProps {
  device: Device;
  /** i18n 翻译函数（由父组件传入，避免每行重复 useI18n） */
  tr: (key: string, params?: Record<string, string | number>) => string;
  onRename: () => void;
  onRevoke: () => void;
  onPurge: () => void;
}

function DeviceRow({ device, tr, onRename, onRevoke, onPurge }: DeviceRowProps) {
  return (
    <div className="rounded-lg border border-text/15 bg-text/[0.06] p-3">
      <div className="flex items-center gap-2">
        <span className="flex-1 truncate text-sm font-semibold text-text">
          {device.device_name || "—"}
        </span>
        {device.revoked && (
          <span className="rounded-full border border-text/15 bg-text/[0.06] px-2 py-0.5 text-[10px] font-medium text-text-muted">
            {tr("devices_revoked_badge")}
          </span>
        )}
      </div>
      <div className="mt-1.5 flex flex-col gap-0.5 text-[10px] text-text-dim">
        <span className="font-mono">
          {tr("devices_paired_at", { time: formatDeviceTime(device.paired_at, tr("devices_unknown_time")) })}
        </span>
        <span className="font-mono">
          {tr("devices_last_active_at", { time: formatDeviceTime(device.last_active_at, tr("devices_unknown_time")) })}
        </span>
      </div>
      <div className="mt-2 flex justify-end gap-2">
        <button
          onClick={onRename}
          disabled={device.revoked}
          className="rounded-lg px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-text/[0.06] hover:text-text disabled:opacity-40 disabled:hover:bg-transparent"
        >
          ✎ {tr("devices_rename")}
        </button>
        {device.revoked ? (
          <button
            onClick={onPurge}
            className="rounded-lg bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger/20"
          >
            🗑 {tr("devices_purge")}
          </button>
        ) : (
          <button
            onClick={onRevoke}
            className="rounded-lg bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger/20"
          >
            🗑 {tr("devices_revoke")}
          </button>
        )}
      </div>
    </div>
  );
}
