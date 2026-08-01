/**
 * 移动设备管理 API 客户端（独立模块）。
 *
 * ⚠️ 此模块仅在开发模式下被 MobileDevicesSettings 组件引用。
 * 构建版本（electron-builder 打包后）中 MobileDevicesSettings 被 tree-shake，
 * 此模块随之被 tree-shake，构建产物中不包含：
 *   - 移动端 API 端点字符串（/api/auth/pair-code、/api/devices 等）
 *   - 设备管理相关类型定义
 *   - restartFastApi 的 Electron IPC 调用
 *
 * 与 api.ts 分离的原因：api.ts 的 `api` 对象被 SettingsPage 其他部分引用，
 * 对象字面量的方法无法被 Rollup 单独 tree-shake，必须拆到独立模块才能彻底移除。
 */

import { get, post, del, patch, lumioGlobal } from "./api";

// ============================================================
// 类型定义（与 src/lumio/mobile_auth.py register_device 返回字段对齐）
// ============================================================

/** 已配对设备（GET /api/devices 列表项） */
export interface Device {
  device_id: string;
  device_name: string;
  device_fingerprint: string;
  /** ISO 8601 UTC 字符串 */
  paired_at: string;
  last_active_at: string;
  /** 已撤销的设备 JWT 立即失效 */
  revoked: boolean;
}

/** /api/auth/pair-code 响应 */
export interface PairCodeResponse {
  pair_code: string;
  expires_in: number;
}

/** /api/auth/server-info 响应（移动端配对前读取，无鉴权） */
export interface ServerInfo {
  /** 是否允许移动端连接（config.allow_mobile_connect） */
  allow_mobile_connect: boolean;
  /** FastAPI 监听 host（"127.0.0.1" 或 "0.0.0.0"） */
  host: string;
  /** FastAPI 监听端口 */
  port: number;
  /** 桌面端局域网 IPv4 列表（移动端据此选择正确 IP 输入） */
  lan_ips: string[];
  /** 桌面端版本号（lumio.__version__） */
  version: string;
  /** HTTPS 证书指纹（SHA-256，用于移动端校验自签证书；HTTP 模式为空串） */
  cert_fingerprint: string;
  /** 是否监听所有接口（host == "0.0.0.0"） */
  listening_all_interfaces: boolean;
}

// ============================================================
// API 方法
// ============================================================

/** 生成 6 位配对码（5 分钟过期）。桌面端无需鉴权，限流 5/min/IP。 */
export function genPairCode(): Promise<PairCodeResponse> {
  return post<PairCodeResponse>("/api/auth/pair-code");
}

/** 获取桌面端服务信息（IP/端口/指纹/版本/允许状态，无鉴权，移动端配对前读取） */
export function getServerInfo(): Promise<ServerInfo> {
  return get<ServerInfo>("/api/auth/server-info");
}

/** 列出所有已配对设备 */
export function listDevices(): Promise<Device[]> {
  return get<Device[]>("/api/devices");
}

/** 重命名设备（PATCH body: {device_name}） */
export function renameDevice(deviceId: string, newName: string): Promise<Device> {
  return patch<Device>(`/api/devices/${encodeURIComponent(deviceId)}`, {
    device_name: newName,
  });
}

/** 撤销设备（吊销 JWT，记录保留）。返回 204 No Content。 */
export function revokeDevice(deviceId: string): Promise<void> {
  return del<void>(`/api/devices/${encodeURIComponent(deviceId)}`);
}

/** 彻底删除已撤销设备记录（从 devices.json 移除）。返回 204 No Content。 */
export function purgeDevice(deviceId: string): Promise<void> {
  return del<void>(`/api/devices/${encodeURIComponent(deviceId)}?purge=1`);
}

/**
 * 重启 FastAPI 子进程（用于"允许移动端连接"开关变化后让新 host 生效）。
 * 仅 Electron 环境可用。重启期间所有 API 请求会失败，前端应显示 loading。
 * 返回 { ok: boolean, error?: string }。
 */
export async function restartFastApi(): Promise<{ ok: boolean; error?: string }> {
  if (!lumioGlobal?.restartFastApi) {
    throw new Error("需要 Electron 环境才能重启 FastAPI");
  }
  return lumioGlobal.restartFastApi();
}
