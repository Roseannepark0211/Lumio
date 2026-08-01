/**
 * FastAPI 客户端 — 与 src/lumio/api_fastapi.py 的 REST API 契约对应。
 * 后续每个页面会按需扩展查询函数（React Query hooks）。
 *
 * 端口动态：Electron 启动时随机分配端口 + token，通过 window.lumio 暴露。
 * 浏览器开发模式（非 Electron）回退到固定 38910。
 */

interface ElectronFileFilter {
  name: string;
  extensions: string[];
}

interface LumioGlobal {
  fastapiBase?: string;
  fastapiToken?: string;
  isElectron?: boolean;
  lumioFileUrl?: (p: string) => string;
  /** 打开文件夹选择对话框（Electron 模式可用） */
  pickFolder?: () => Promise<string>;
  /** 打开文件选择对话框（Electron 模式可用，支持多选） */
  pickFiles?: (filters?: ElectronFileFilter[]) => Promise<string[]>;
  /** 托盘菜单 IPC 桥接 */
  tray?: {
    showWindow: () => void;
    openDir: () => void;
    navigate: (page: string) => void;
    toggleTheme: () => void;
    pauseAll: () => void;
    quit: () => void;
    close: () => void;
    cancelClose: () => void;
    minimizeToTray: () => void;
    quitApp: () => void;
  };
  /** 监听托盘菜单导航事件（主进程 → 渲染进程） */
  onNavigate?: (callback: (page: string) => void) => void;
  /** 自动更新 IPC 桥接（Electron 模式可用） */
  updater?: {
    check: () => Promise<CheckUpdateResult>;
    download: () => Promise<{ ok: boolean; error: string | null }>;
    quitAndInstall: () => Promise<{ ok: boolean }>;
    onEvent: (callback: (channel: string, data: any) => void) => void;
  };
}

// ============================================================
// 自动更新类型定义（与 electron/updater.ts 对齐）
// ============================================================

export interface UpdateInfo {
  version: string;
  releaseNotes: string | null;
  releaseName: string | null;
  releaseDate: string | null;
}

export interface CheckUpdateResult {
  hasUpdate: boolean;
  info: UpdateInfo | null;
  error: string | null;
}

export interface DownloadProgress {
  percent: number;
  transferredBytes: number;
  totalBytes: number;
  bytesPerSecond: number;
}

/** 自动更新事件通道名（与 electron/updater.ts sendToRenderer 对齐） */
export type UpdateEventChannel =
  | "update:checking"
  | "update:available"
  | "update:not-available"
  | "update:download-progress"
  | "update:downloaded"
  | "update:error";

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
 *  w/h > 0 时让后端用 PIL 缩放，节省带宽（适用于小卡片缩略图）。
 *  persist=true 时后端写入 .bin+.meta 缓存（仅用于已下载完成的素材库/历史封面），
 *  其他场景（Home 预览/搜索结果/收件箱）传 false 避免缓存膨胀。
 */
export function thumbProxyUrl(remoteUrl: string, w = 0, h = 0, persist = false): string {
  if (!remoteUrl) return "";
  const q = new URLSearchParams();
  q.set("url", remoteUrl);
  if (w > 0) q.set("w", String(w));
  if (h > 0) q.set("h", String(h));
  if (persist) q.set("persist", "1");
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
  /** 该素材已加入的 Collection id 列表（按分类筛选用） */
  collection_ids: number[];
}

/** 素材库 Collection（与 api_fastapi.py /api/library/collections 对齐） */
export interface LibraryCollection {
  id: number;
  name: string;
  /** 该 Collection 下的素材数量（后端动态计算） */
  count: number;
  /** 总字节数（后端动态计算） */
  total_size: number;
}

/** 历史记录条目（与 api_fastapi.py _history_to_dict 对齐） */
export interface HistoryRecord {
  id: string;
  url: string;
  title: string;
  platform: string;
  author: string;
  file_path: string;
  file_size: number;
  thumbnail_url: string;
  media_type: string;
  success: boolean;
  error: string;
  download_time: string;
  post_time: string;
  batch_id: string;
}

/** 收件箱条目（与 api_fastapi.py _inbox_item_to_dict 对齐） */
export interface InboxItem {
  id: string;
  url: string;
  direct_url: string;
  title: string;
  platform: string;
  author: string;
  thumbnail_url: string;
  /** 模型字段名为 type（url/video/image） — 这里同时给出 type 和 media_type 两个别名 */
  type: string;
  media_type: string;
  /** new / queued / downloaded / archived / failed */
  status: string;
  /** browser / telegram / manual */
  source: string;
  post_time: string;
  duration: number;
  /** 收件箱捕获时间（QML 使用此字段） */
  captured_at: string;
  created_at: string;
  content: string;
  error_message: string;
}

/** 统计数据（与 api_fastapi.py /api/stats 对齐） */
export interface StatsResponse {
  total_downloads: number;
  total_size: number;
  /** 0-100 的百分比，例如 87.5 */
  success_rate: number;
  today_count: number;
  /** 平台 → 下载次数的映射 */
  platforms: Record<string, number>;
}

/** 通知项（与 notification_manager.py Notification dataclass 对齐） */
export interface NotificationItem {
  id: string;
  category: string;       // deps / env / update / system / inbox
  type: string;           // warning / info / update / tip
  priority: string;       // critical / high / normal / low
  title: string;
  message: string;
  action: string;         // "open_page:settings" / "open_url:xxx" / "retry_task:id"
  action_text: string;    // 按钮文字
  source_key: string;
  expires_at: string;
  group_key: string;
  dismissable: boolean;
  read: boolean;
  created_at: string;
}

// ============================================================
// SettingsPage 相关类型（与 api_fastapi.py settings 端点对齐）
// ============================================================

/** Cookie 总体状态 + 各平台单独状态 */
export interface CookieStatusResponse {
  /** overall: missing / valid / warning / expired */
  overall: string;
  /** 各平台单独状态：{ "instagram": "valid", "x": "missing", ... } */
  platforms?: Record<string, string>;
  error?: string;
}

/** Telegram 状态（pair_code / bound_device / is_running） */
export interface TelegramState {
  pair_code: string;
  /** 绑定设备信息（无绑定为 null） */
  bound_device: {
    telegram_user_id: string;
    username: string;
    first_name: string;
  } | null;
  is_running: boolean;
  error?: string;
}

/** Telegram Token 验证结果 */
export interface TelegramValidateResult {
  ok: boolean;
  username?: string;
  error?: string;
}

// ============================================================
// SettingsPage: 移动设备管理（FastAPI 安全阶段 2）
// 与 src/lumio/mobile_auth.py register_device 返回字段对齐
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

/** Apify 配置状态（持久） */
export interface ApifyStatus {
  token_configured: boolean;
  actor_configured: boolean;
  /** connected = token+actor 都配置且已验证有效 */
  connected: boolean;
  verified: boolean;
  /** enabled = instagram_mode == "api" */
  enabled: boolean;
  token_preview: string;
  actor_id: string;
  usage_usd: number | null;
  plan_credits_usd: number | null;
  plan_name: string | null;
  usage_updated: string | null;
}

/** Apify 用量数据（apify_usage_updated WS 事件 payload / apify_status 返回） */
export interface ApifyUsage {
  usage_usd?: number;
  plan_credits_usd?: number;
  plan_name?: string;
  usage_updated?: string;
  error?: string;
}

/** Apify Token 验证结果 */
export interface ApifyValidateResult {
  ok: boolean;
  error?: string;
}

/** 缓存目录统计（get_cache_stats 返回） */
export interface CacheStats {
  _root?: string;
  inbox_media?: CacheDirStat;
  thumbs?: CacheDirStat;
  provider_cache?: CacheDirStat;
  preview?: CacheDirStat;
  error?: string;
  [k: string]: CacheDirStat | string | undefined;
}

export interface CacheDirStat {
  path?: string;
  size_bytes?: number;
  file_count?: number;
  deleted?: number;
  freed?: number;
}

/** 版本检查响应（/api/check-update）—— 旧 FastAPI 端点返回的格式
 *  注意：与 electron-updater 的 CheckUpdateResult 不同（前者用于后端 API 兼容） */
export interface CheckUpdateApiResponse {
  current?: string;
  latest?: string;
  has_update?: boolean;
  release_url?: string;
  release_name?: string;
  release_body?: string;
  published_at?: string;
  error?: string;
}

// ============================================================
// HomePage 相关类型（与 QML _video_info_to_json 对齐）
// ============================================================

/** Live Photo 双文件结构 */
export interface LivePhotoData {
  image?: string;
  video?: string;
  cover?: string;
}

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
  /** Live Photo 双文件（小红书/微博实况图，含视频流） */
  live_photo?: LivePhotoData | null;
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

// FastAPI 就绪等待 + 自动重试
// 问题背景：Electron 打包模式下，前端页面 ready-to-show 时 FastAPI 可能还在启动中
// （PyInstaller 解压 + Python 启动需要 3-8 秒）。此时所有 fetch 请求会收到
// net::ERR_CONNECTION_REFUSED，导致页面显示"加载失败"且不会自动重试。
//
// 解决方案：在 get/post/put/delete 中检测连接失败，自动重试。
// 重试策略：
//   - 最多重试 30 次，每次间隔 500ms（总等待最多 15 秒）
//   - 只重试 TypeError（网络错误：连接拒绝、连接重置等），不重试 HTTP 错误（4xx/5xx）
//   - FastAPI ready 后的请求不受影响（首次就成功）
async function fetchWithRetry(
  url: string,
  init: RequestInit,
  maxRetries = 30,
  retryDelayMs = 500
): Promise<Response> {
  let lastError: unknown;
  for (let i = 0; i < maxRetries; i++) {
    try {
      const r = await fetch(url, init);
      return r;
    } catch (e) {
      lastError = e;
      // TypeError = 网络错误（连接拒绝/重置/超时），可能是 FastAPI 还没 ready
      // HTTP 错误（4xx/5xx）不会进这里，因为 fetch 不会对 HTTP 错误状态码 throw
      if (e instanceof TypeError) {
        // FastAPI 还没 ready，等待后重试
        await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
        continue;
      }
      // 其他错误直接抛出
      throw e;
    }
  }
  throw lastError;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetchWithRetry(`${BASE}${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetchWithRetry(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  return r.json() as Promise<T>;
}

async function put<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetchWithRetry(`${BASE}${path}`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  return r.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const r = await fetchWithRetry(`${BASE}${path}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  // 204 No Content / 空 body 时不解析 JSON
  if (r.status === 204) return undefined as T;
  const text = await r.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

async function patch<T>(path: string, body?: unknown): Promise<T> {
  const hasBody = body !== undefined;
  const r = await fetchWithRetry(`${BASE}${path}`, {
    method: "PATCH",
    headers: authHeaders(hasBody ? { "Content-Type": "application/json" } : undefined),
    body: hasBody ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${path}`);
  // 204 No Content / 空 body 时不解析 JSON
  if (r.status === 204) return undefined as T;
  const text = await r.text();
  return (text ? JSON.parse(text) : undefined) as T;
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
  toggleFavorite: (itemId: string) =>
    post<{ is_favorite: boolean }>(`/api/library/items/${encodeURIComponent(itemId)}/favorite`),
  deleteLibraryItem: (itemId: string) =>
    del<{ ok: boolean }>(`/api/library/items/${encodeURIComponent(itemId)}`),

  // —— 素材库 Collection ——
  getCollections: () => get<LibraryCollection[]>("/api/library/collections"),
  createCollection: (name: string) =>
    post<{ id: number }>(`/api/library/collections?name=${encodeURIComponent(name)}`),
  deleteCollection: (cid: number) =>
    del<{ ok: boolean }>(`/api/library/collections/${cid}`),
  renameCollection: (cid: number, name: string) =>
    patch<{ ok: boolean }>(`/api/library/collections/${cid}?name=${encodeURIComponent(name)}`),
  addItemToCollection: (itemId: string, cid: number) =>
    post<{ ok: boolean }>(`/api/library/items/${encodeURIComponent(itemId)}/collections/${cid}`),
  removeItemFromCollection: (itemId: string, cid: number) =>
    del<{ ok: boolean }>(`/api/library/items/${encodeURIComponent(itemId)}/collections/${cid}`),
  /** 获取某素材已加入的 Collection id 列表 */
  getItemCollections: (itemId: string) =>
    get<number[]>(`/api/library/items/${encodeURIComponent(itemId)}/collections`),

  // —— 历史记录 ——
  getHistory: () => get<HistoryRecord[]>("/api/history"),
  deleteHistory: (id: string) => del<{ ok: boolean }>(`/api/history/${encodeURIComponent(id)}`),
  clearHistory: () => del<{ ok: boolean }>("/api/history"),

  // —— 收件箱 ——
  getInbox: () => get<InboxItem[]>("/api/inbox"),
  getInboxUnreadCount: () => get<{ count: number }>("/api/inbox/unread-count"),
  /** 单条入队下载（status 为 new/failed 时可用） */
  inboxDownload: (itemId: string) =>
    post<{ ok: boolean; task_id: string }>(`/api/inbox/items/${encodeURIComponent(itemId)}/download`),
  /** 批量入队下载 */
  inboxBatchDownload: (ids: string[]) =>
    post<{ ok: boolean }>("/api/inbox/batch-download", { ids }),
  /** 归档单条 */
  inboxArchive: (itemId: string) =>
    post<{ ok: boolean }>(`/api/inbox/items/${encodeURIComponent(itemId)}/archive`),
  /** 删除单条 */
  inboxDelete: (itemId: string) =>
    del<{ ok: boolean }>(`/api/inbox/items/${encodeURIComponent(itemId)}`),
  /** 批量删除 */
  inboxBatchDelete: (ids: string[]) =>
    post<{ ok: boolean }>("/api/inbox/batch-delete", { ids }),
  /** 清空所有已下载 / 已归档的条目 */
  inboxClearCompleted: () =>
    post<{ ok: boolean; deleted: number }>("/api/inbox/clear-completed"),

  // —— 统计 ——
  getStats: () => get<StatsResponse>("/api/stats"),

  // —— 通知 ——
  getNotifications: () => get<NotificationItem[]>("/api/notifications"),
  getUnreadCount: () => get<{ count: number }>("/api/notifications/unread-count"),
  markAllRead: () => post<{ ok: boolean }>("/api/notifications/read-all"),
  markRead: (id: string) => post<{ ok: boolean }>(`/api/notifications/${id}/read`),
  clearRead: () => post<{ ok: boolean }>("/api/notifications/clear-read"),
  dismiss: (id: string) => post<{ ok: boolean }>(`/api/notifications/${id}/dismiss`),

  // —— 文件操作 ——
  /** 打开文件。source: "library" / "history" — 缺失时后端会推 file_missing 事件。 */
  openFile: (path: string, source: string = "") =>
    post<{ ok: boolean; error?: string }>("/api/open-file", { path, source }),
  /** 打开文件所在目录。source 同上。 */
  openFolder: (path: string, source: string = "") =>
    post<{ ok: boolean; error?: string }>("/api/open-folder", { path, source }),
  /** 解析预览主文件路径（mixed/目录型素材扫描文件夹找主视频/图片）。 */
  resolvePreviewTarget: (filePath: string, mediaType: string = "") =>
    post<{ path: string; media_type: string }>("/api/library/preview-target", {
      file_path: filePath,
      media_type: mediaType,
    }),
  /** 列出文件夹内所有可预览媒体（按 video → image → audio 排序），用于上下项切换。 */
  listPreviewItems: (filePath: string) =>
    post<{ items: Array<{ path: string; media_type: string }> }>("/api/library/preview-items", {
      file_path: filePath,
      media_type: "",
    }),
  /** 在系统默认浏览器中打开外部 URL（InboxPage 的"打开原网页"按钮） */
  openExternalUrl: (url: string) =>
    post<{ ok: boolean; error?: string }>("/api/open-external-url", { url }),

  // —— SettingsPage: 配置读写 ——
  /** 设置单个 config 顶层键 */
  setConfig: (key: string, value: unknown) =>
    put<{ ok: boolean }>(`/api/config/${encodeURIComponent(key)}`, { value }),
  /** 设置嵌套 config（如 cache_management.auto_clean） */
  setNestedConfig: (parentKey: string, updates: Record<string, unknown>) =>
    put<{ ok: boolean }>(`/api/config/nested/${encodeURIComponent(parentKey)}`, { updates }),

  // —— 主题 / 语言 / i18n ——
  setTheme: (theme: string) =>
    put<{ theme: string }>("/api/theme", { theme }),
  setLang: (lang: string) =>
    put<{ lang: string }>("/api/lang", { lang }),
  /** 拉取完整翻译字典（前端启动时一次性缓存到内存）。
   *  返回结构：{ zh: {key: text}, en: {key: text} } */
  getI18n: () => get<Record<string, Record<string, string>>>("/api/i18n"),

  // —— SettingsPage: Cookie 管理 ——
  getCookieStatus: () => get<CookieStatusResponse>("/api/cookie/status"),
  clearCookie: () => post<{ ok: boolean; error?: string }>("/api/cookie/clear"),
  importCookie: (paths: string[]) =>
    post<{ ok: boolean; imported?: number; error?: string }>("/api/cookie/import", { paths }),

  // —— SettingsPage: Telegram ——
  validateTelegram: (token: string, proxy: string = "") =>
    post<TelegramValidateResult>("/api/telegram/validate", { token, proxy }),
  getTelegramState: () => get<TelegramState>("/api/telegram/state"),
  getTelegramPairCode: () =>
    get<{ pair_code?: string; error?: string }>("/api/telegram/pair-code"),
  unlinkTelegram: () => post<{ ok: boolean; error?: string }>("/api/telegram/unlink"),

  // —— SettingsPage: Apify ——
  validateApify: (token: string, actorId: string) =>
    post<ApifyValidateResult>("/api/apify/validate", { token, actor_id: actorId }),
  getApifyStatus: () => get<ApifyStatus>("/api/apify/status"),
  refreshApifyUsage: () => post<{ ok: boolean; cached?: boolean }>("/api/apify/refresh-usage"),
  forceRefreshApifyUsage: () => post<{ ok: boolean }>("/api/apify/force-refresh-usage"),

  // —— SettingsPage: 移动设备管理（FastAPI 安全阶段 2） ——
  /** 生成 6 位配对码（5 分钟过期）。桌面端无需鉴权，限流 5/min/IP。 */
  genPairCode: () => post<PairCodeResponse>("/api/auth/pair-code"),
  /** 列出所有已配对设备 */
  listDevices: () => get<Device[]>("/api/devices"),
  /** 重命名设备（PATCH body: {device_name}） */
  renameDevice: (deviceId: string, newName: string) =>
    patch<Device>(`/api/devices/${encodeURIComponent(deviceId)}`, { device_name: newName }),
  /** 撤销设备（吊销 JWT，记录保留）。返回 204 No Content。 */
  revokeDevice: (deviceId: string) =>
    del<void>(`/api/devices/${encodeURIComponent(deviceId)}`),

  /** 彻底删除已撤销设备记录（从 devices.json 移除）。返回 204 No Content。 */
  purgeDevice: (deviceId: string) =>
    del<void>(`/api/devices/${encodeURIComponent(deviceId)}?purge=1`),

  // —— SettingsPage: 缓存管理 ——
  getCacheStats: () => get<CacheStats>("/api/cache/stats"),
  cleanCacheByRules: () => post<{ ok: boolean }>("/api/cache/clean-by-rules"),
  forceClearCache: () => post<{ ok: boolean }>("/api/cache/force-clear"),

  // —— SettingsPage: 剪贴板 ——
  copyToClipboard: (text: string) =>
    post<{ ok: boolean; error?: string }>("/api/clipboard/copy", { text }),

  // —— SettingsPage: 版本检查 ——
  checkUpdate: () => get<CheckUpdateApiResponse>("/api/check-update"),

  // —— SettingsPage: 文件/文件夹对话框（走 Electron IPC，非 FastAPI） ——
  /**
   * 打开文件夹选择对话框。
   * 仅 Electron 环境可用（依赖 preload.ts 注入的 window.lumio.pickFolder）。
   * 浏览器开发模式（http://localhost:5173 直接访问）下不可用，会 throw。
   */
  pickFolder: async (): Promise<string> => {
    if (!lumioGlobal?.pickFolder) {
      throw new Error(
        "需要 Electron 环境（请运行 npm run dev:electron 启动桌面应用，不要在浏览器标签页里访问 localhost:5173）"
      );
    }
    return lumioGlobal.pickFolder();
  },
  /**
   * 打开文件选择对话框（支持多选）。
   * 仅 Electron 环境可用。
   */
  pickFiles: async (filters?: ElectronFileFilter[]): Promise<string[]> => {
    if (!lumioGlobal?.pickFiles) {
      throw new Error(
        "需要 Electron 环境（请运行 npm run dev:electron 启动桌面应用，不要在浏览器标签页里访问 localhost:5173）"
      );
    }
    return lumioGlobal.pickFiles(filters);
  },
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
  | "library_thumbnail_ready"
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
  | "file_missing"
  // 心跳协议帧（非业务事件，subscribeEvents 内部消费，不传递给业务回调）
  | "ping"
  | "pong";

export interface AppEvent<T = unknown> {
  type: EventType;
  data: T;
  ts: number;
}

/**
 * 订阅 FastAPI WebSocket 事件流。
 *
 * 健壮性设计（社区最佳实践）：
 * - **心跳保活**：后端每 25s 发应用层 ping；前端收到后回 pong。
 *   若 60s 内未收到任何消息（含 ping），认为连接已断（NAT/路由器静默切断），
 *   主动 close 并触发重连。
 * - **指数退避重连**：断开后 1s → 2s → 4s → 8s → 16s → 30s（上限）重试，
 *   避免短时间大量重连风暴；重连成功后退避重置。
 *
 * 返回 unsubscribe 函数。
 */
export function subscribeEvents(
  onEvent: (e: AppEvent) => void,
  onError?: (e: Event) => void
): () => void {
  // WebSocket URL 需要把 http base 转成 ws
  // 必须带 ?token=xxx：后端 ws_events 在 accept() 前校验 token，
  // 缺失会 close(code=4401)，ASGI 协议在 accept 前 close 会返回 HTTP 403
  const wsBase = BASE.replace(/^http/, "ws");
  const tokenQuery = TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : "";
  const url = `${wsBase}/ws/events${tokenQuery}`;

  // 心跳超时阈值：后端每 25s 发一次 ping，2 个周期内必须收到任何消息
  const HEARTBEAT_TIMEOUT_MS = 60_000;
  // 重连退避：1s → 2s → 4s → 8s → 16s → 30s（上限）
  const MIN_BACKOFF_MS = 1_000;
  const MAX_BACKOFF_MS = 30_000;

  let ws: WebSocket | null = null;
  let closedByUser = false;
  let backoffMs = MIN_BACKOFF_MS;
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const clearHeartbeat = () => {
    if (heartbeatTimer) {
      clearTimeout(heartbeatTimer);
      heartbeatTimer = null;
    }
  };
  const scheduleHeartbeat = () => {
    clearHeartbeat();
    heartbeatTimer = setTimeout(() => {
      // 60s 没收到任何消息，主动断开触发重连
      ws?.close();
    }, HEARTBEAT_TIMEOUT_MS);
  };

  const connect = () => {
    ws = new WebSocket(url);

    ws.onopen = () => {
      // 连接成功：重置退避
      backoffMs = MIN_BACKOFF_MS;
      scheduleHeartbeat();
    };

    ws.onmessage = (e) => {
      // 任何消息都视为心跳有效（包括 ping）
      scheduleHeartbeat();
      try {
        const evt = JSON.parse(e.data) as AppEvent;
        // 应用层 ping/pong：后端发 ping，前端回 pong
        if (evt.type === "ping") {
          try {
            ws?.send(JSON.stringify({ type: "pong", data: null, ts: Date.now() }));
          } catch {
            // send 失败说明连接已断，让心跳超时机制处理
          }
          return;
        }
        onEvent(evt);
      } catch {
        // ignore parse error
      }
    };

    ws.onerror = (e) => {
      onError?.(e);
    };

    ws.onclose = () => {
      clearHeartbeat();
      if (closedByUser) return;
      // 指数退避重连
      reconnectTimer = setTimeout(() => {
        backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS);
        connect();
      }, backoffMs);
    };
  };

  connect();

  return () => {
    closedByUser = true;
    clearHeartbeat();
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) {
      ws.onclose = null;  // 阻止 onclose 触发重连
      ws.close();
    }
  };
}
