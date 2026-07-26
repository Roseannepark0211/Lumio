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
  lumioFileUrl?: (p: string) => string;
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

/**
 * 把本地文件绝对路径转成 lumio-file:// URL（Electron 主进程已注册 protocol）。
 * React 端用 <video src={lumioFileUrl(path)}> 播放本地视频。
 * 非 Electron 环境返回空字符串。
 */
export function lumioFileUrl(p: string): string {
  if (!p) return "";
  if (lumioGlobal?.lumioFileUrl) return lumioGlobal.lumioFileUrl(p);
  // 非 Electron 环境回退：直接返回 file:// URL（仅用于调试）
  return `file:///${p.replace(/\\/g, "/")}`;
}

/** 把远程图片 URL 包装成 /api/thumb-proxy?url=...&token=... 形式。
 *  浏览器原生 <img src> 不带 X-Lumio-Token header，必须用 query token 兜底。
 */
export function thumbProxyUrl(remoteUrl: string): string {
  if (!remoteUrl) return "";
  const q = new URLSearchParams();
  q.set("url", remoteUrl);
  if (TOKEN) q.set("token", TOKEN);
  return `${BASE}/api/thumb-proxy?${q.toString()}`;
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
// HomePage 相关类型（与 QML _video_info_to_json 对齐）
// ============================================================

/** 单个媒体项（多图/多视频帖的子项） */
export interface MediaItem {
  url: string;
  is_video: boolean;
  media_type: string;
  width: number;
  height: number;
  extension: string;
  size: number;
  quality: string;
  filename: string;
}

/** 可选格式（YouTube 等多档位） */
export interface FormatOption {
  format_id: string;
  type: string;       // "video" | "audio" | "mixed"
  label: string;
  height: number;
}

/** URL 解析结果（VideoInfo） */
export interface VideoInfo {
  title: string;
  url: string;
  thumbnail: string;
  duration: number;
  platform: string;
  author: string;
  post_time: string;
  items: MediaItem[];
  formats: FormatOption[];
}

/** X-Sou 搜索结果项 */
export interface XSouResult {
  video_url: string;
  video_cover: string;
  content: string;     // 推文文本（前 80 字符作为标题）
  tweet_url?: string;
  author?: string;
}

/** X-Sou 搜索响应（searchCompleted 信号 payload） */
export interface XSouSearchPayload {
  data: XSouResult[];
  total: number;
}

/** 解析 URL 响应（parseCompleted 信号 payload） */
export interface ParseCompletedPayload {
  info: VideoInfo;
}

/** 预览进度（previewProgress 信号 payload，已修复为双字段） */
export interface PreviewProgressPayload {
  downloaded: number;
  total: number;
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

async function put<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  return r.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  return r.json() as Promise<T>;
}

// ============================================================
// 请求 ID 生成（用于异步 WS 事件关联）
// ============================================================

let _reqCounter = 0;
function nextReqId(prefix = "req"): string {
  _reqCounter += 1;
  return `${prefix}-${Date.now()}-${_reqCounter}`;
}

export const api = {
  // —— 健康检查 ——
  getHealth: () => get<HealthResponse>("/api/health"),

  // —— 下载队列 ——
  getQueue: () => get<QueueTask[]>("/api/queue"),
  startTask: (id: string) => post<{ ok: boolean }>(`/api/queue/tasks/${id}/start`),
  pauseTask: (id: string) => post<{ ok: boolean }>(`/api/queue/tasks/${id}/pause`),
  resumeTask: (id: string) => post<{ ok: boolean }>(`/api/queue/tasks/${id}/resume`),
  cancelTask: (id: string) => post<{ ok: boolean }>(`/api/queue/tasks/${id}/cancel`),
  retryTask: (id: string) => post<{ ok: boolean }>(`/api/queue/tasks/${id}/retry`),
  deleteTask: (id: string) => del<{ ok: boolean }>(`/api/queue/tasks/${id}`),
  startAll: () => post<{ ok: boolean }>("/api/queue/start-all"),
  pauseAll: () => post<{ ok: boolean }>("/api/queue/pause-all"),
  resumeAll: () => post<{ ok: boolean }>("/api/queue/resume-all"),
  /** 检查 URL 是否已在素材库中（非阻断，返回 true 仍可继续下载） */
  checkUrlDuplicate: (url: string) =>
    get<{ duplicate: boolean }>(`/api/queue/check-url-duplicate?url=${encodeURIComponent(url)}`),

  // —— HomePage: URL 解析 + 入队 ——
  /**
   * 触发后台 URL 解析。结果通过 WebSocket 的 `parse_completed` / `parse_failed` 事件回传。
   * 返回的 request_id 用于关联 WS 事件。
   */
  parseUrl: (url: string, requestId?: string) =>
    post<{ ok: boolean; request_id: string }>("/api/parse-url", {
      url,
      request_id: requestId || nextReqId("parse"),
    }),

  /** 整帖入队（带格式选择） */
  addDownloadTask: (params: {
    info: VideoInfo;
    format_id: string;
    format_type: string;
    custom_name: string;
    output_dir?: string;
  }) =>
    post<{ task_id: string }>("/api/queue/task/from-info", {
      info: params.info,
      format_id: params.format_id,
      format_type: params.format_type,
      custom_name: params.custom_name,
      output_dir: params.output_dir || "",
    }),

  /** 直链入队（X-Sou 搜索结果 / 多图帖单项） */
  addDirectDownloadTask: (params: {
    url: string;
    title: string;
    platform: string;
    thumbnail?: string;
    is_video: boolean;
    author?: string;
  }) =>
    post<{ task_id: string }>("/api/queue/task/from-direct", {
      url: params.url,
      title: params.title,
      platform: params.platform,
      thumbnail: params.thumbnail || "",
      is_video: params.is_video,
      author: params.author || "",
    }),

  // —— HomePage: X-Sou 搜索 ——
  /**
   * 触发后台 X-Sou 搜索。结果通过 WebSocket 的 `search_completed` / `search_failed` 事件回传。
   * `@username` 在后端自动转 `from:username`。
   */
  searchXSou: (query: string, page: number, limit = 20, requestId?: string) =>
    post<{ ok: boolean; request_id: string }>("/api/search-xsou", {
      query,
      page,
      limit,
      request_id: requestId || nextReqId("search"),
    }),

  // —— HomePage: X-Sou 视频预览 ——
  /**
   * 触发后台下载 video.twimg.com 视频到 ~/.lumio/cache/preview/。
   * 进度通过 WS `preview_progress`，完成通过 `preview_ready`，失败通过 `preview_failed`。
   */
  previewXVideo: (videoUrl: string) =>
    post<{ ok: boolean }>("/api/preview-x-video", { video_url: videoUrl }),
  /** 取消正在进行的 X-Sou 视频预览下载 */
  cancelPreview: () => post<{ ok: boolean; error?: string }>("/api/preview-cancel"),

  // —— HomePage: 配置 / 剪贴板 ——
  /** 获取 config（X-Sou 开关等） */
  getConfig: () => get<Record<string, unknown>>("/api/config"),
  /** 读系统剪贴板文本 */
  getClipboardText: () => get<{ text: string }>("/api/clipboard/text"),

  // —— 素材库 ——
  getLibrary: () => get<LibraryItem[]>("/api/library"),
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
