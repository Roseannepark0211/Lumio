/**
 * FastAPI 客户端 — 与 src/lumio/api_fastapi.py 的 REST API 契约对应。
 * 后续每个页面会按需扩展查询函数（React Query hooks）。
 *
 * 端口动态：Electron 启动时随机分配端口 + token，通过 window.lumio 暴露。
 * 浏览器开发模式（非 Electron）回退到固定 38910。
 */

interface LumioGlobal {
  fastapiBase?: string;
  fastapiToken?: string;
  isElectron?: boolean;
}

const lumioGlobal = (typeof window !== "undefined" ? (window as unknown as { lumio?: LumioGlobal }).lumio : undefined);

const BASE = lumioGlobal?.fastapiBase || "http://127.0.0.1:38910";
const TOKEN = lumioGlobal?.fastapiToken || "";

/** 统一请求头（带 token 鉴权） */
function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    ...(TOKEN ? { "X-Lumio-Token": TOKEN } : {}),
    ...(extra || {}),
  };
}

// ============================================================
// 类型定义（与 api_fastapi.py 的 Pydantic 模型 / 返回 dict 对齐）
// ============================================================

export interface HealthResponse {
  ok: boolean;
  version: string;
  managers: {
    download: boolean;
    inbox: boolean;
    library: boolean;
    history: boolean;
    notification: boolean;
  };
}

export interface QueueTask {
  task_id: string;
  url: string;
  direct_url: string;
  title: string;
  status: string;
  progress: number;
  speed: string;
  filename: string;
  thumbnail_url: string;
  platform: string;
  author: string;
  post_time: string;
  output_dir: string;
  custom_name: string;
  error: string;
  media_type: string;
  retry_count: number;
  media_items_json: string;
  batch_id: string;
}

export interface LibraryItem {
  id: string;
  title: string;
  url: string;
  platform: string;
  author: string;
  file_path: string;
  file_size: number;
  media_type: string;
  is_favorite: boolean;
  post_time: string;
  created_at: string;
  thumbnail_url: string;
  thumbnail_path: string;
  folder_path: string;
  batch_id: string;
  content_hash: string;
  duration: number;
}

// ============================================================
// API 客户端
// ============================================================

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  return r.json() as Promise<T>;
}

export const api = {
  getHealth: () => get<HealthResponse>("/api/health"),
  getQueue: () => get<QueueTask[]>("/api/queue"),
  getLibrary: () => get<LibraryItem[]>("/api/library"),
  // 后续按页面需求扩展：parse-url / start-task / pause-task / ...
  startTask: (id: string) => post<{ ok: boolean }>(`/api/queue/tasks/${id}/start`),
  pauseTask: (id: string) => post<{ ok: boolean }>(`/api/queue/tasks/${id}/pause`),
};

// ============================================================
// WebSocket 事件流
// ============================================================

export type EventType =
  | "task_added"
  | "task_started"
  | "task_progress"
  | "task_finished"
  | "task_status_changed"
  | "queue_changed"
  | "batch_progress"
  | "history_record_added"
  | "library_record_added"
  | "conflict_ask"
  | "notification_changed"
  | "theme_changed"
  | "lang_changed"
  | "config_changed"
  | "inbox_changed"
  | "library_changed"
  | "history_changed"
  | "parse_completed"
  | "parse_failed"
  | "search_completed"
  | "search_failed"
  | "preview_ready"
  | "preview_progress"
  | "preview_failed"
  | "apify_usage_updated"
  | "cache_cleaned"
  | "toast"
  | "file_missing";

export interface AppEvent<T = unknown> {
  type: EventType;
  data: T;
  ts: number;
}

/**
 * 订阅 FastAPI WebSocket 事件流。
 * 返回 unsubscribe 函数。
 */
export function subscribeEvents(
  onEvent: (e: AppEvent) => void,
  onError?: (e: Event) => void
): () => void {
  // WebSocket URL 需要把 http base 转成 ws
  const wsBase = BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/ws/events`);
  ws.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {
      // ignore parse error
    }
  };
  ws.onerror = (e) => onError?.(e);
  return () => ws.close();
}
