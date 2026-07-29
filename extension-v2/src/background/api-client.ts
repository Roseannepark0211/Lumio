/**
 * Lumio FastAPI 客户端 — background 与 Lumio 桌面客户端通信
 *
 * 阶段 1：仅 /health + /capture
 * 阶段 3：加 /inbox/count + WebSocket
 */
import type { CapturePayload, CaptureResult, Platform } from "../types";

/** 平台检测（与原 background.js 一致，含国内平台） */
export function detectPlatform(url: string): Platform {
  if (!url) return "";
  if (url.includes("youtube.com") || url.includes("youtu.be")) return "youtube";
  if (url.includes("instagram.com")) return "instagram";
  if (url.includes("x.com") || url.includes("twitter.com")) return "x";
  if (url.includes("bilibili.com") || url.includes("b23.tv")) return "bilibili";
  if (url.includes("kuaishou.com")) return "kuaishou";
  if (
    url.includes("xiaohongshu.com") ||
    url.includes("xhslink.com") ||
    url.includes("xhslink.cn")
  ) {
    return "xiaohongshu";
  }
  if (url.includes("douyin.com") || url.includes("v.douyin.com")) return "douyin";
  return "";
}

/** 从 URL 提取作者名（保留原 background.js 逻辑） */
export function extractAuthorFromUrl(url: string): string {
  if (!url) return "";
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    const host = u.hostname;

    if (host.includes("instagram.com") && parts.length >= 1) {
      const igReserved = ["p", "reel", "tv", "explore", "accounts", "direct", "stories"];
      if (!igReserved.includes(parts[0]) && parts[0] !== "") return parts[0];
      return "";
    }

    if ((host.includes("x.com") || host.includes("twitter.com")) && parts.length >= 1) {
      const reserved = ["i", "search", "home", "notifications", "explore", "settings", "messages"];
      if (!reserved.includes(parts[0])) return parts[0];
      return "";
    }

    if (host.includes("youtube.com")) {
      if (parts[0]?.startsWith("@")) return parts[0].slice(1);
      if (parts[0] === "channel" || parts[0] === "c" || parts[0] === "user") return parts[1] || "";
    }

    if (host.includes("bilibili.com")) {
      if (parts[0] === "space") return parts[1] || "";
    }

    if (host.includes("kuaishou.com")) {
      if (parts[0] === "profile") return parts[1] || "";
    }

    if (host.includes("xiaohongshu.com")) {
      if (parts[0] === "user" && parts[1] === "profile") return parts[2] || "";
    }

    if (host.includes("douyin.com")) {
      if (parts[0] === "user") return parts[1] || "";
    }
  } catch {
    /* ignore */
  }
  return "";
}

export class LumioClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  updateBaseUrl(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  /** 健康检查（3 秒超时） */
  async health(): Promise<boolean> {
    try {
      const resp = await fetch(`${this.baseUrl}/health`, {
        signal: AbortSignal.timeout(3000),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }

  /** 发送到 Inbox */
  async capture(payload: CapturePayload): Promise<CaptureResult> {
    try {
      const resp = await fetch(`${this.baseUrl}/capture`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        return { success: false, error: `HTTP ${resp.status}` };
      }
      return (await resp.json()) as CaptureResult;
    } catch (err) {
      return { success: false, error: err instanceof Error ? err.message : String(err) };
    }
  }
}
