/**
 * Cloudflare Pages Function — GitHub API 反代（中间件版）
 *
 * 路径格式：
 *   /api/gh-api/repos/<owner>/<repo>/releases
 *   /api/gh-api/repos/<owner>/<repo>/releases/latest
 *
 * 示例：
 *   /api/gh-api/repos/Roseannepark0211/Lumio/releases?per_page=8
 *   → 代理 https://api.github.com/repos/Roseannepark0211/Lumio/releases?per_page=8
 *
 * 用途：
 *   官网更新日志模块（changelog.ts）在客户端 fetch GitHub Releases API。
 *   国内无代理用户无法直连 api.github.com，
 *   通过此反代走 Cloudflare CDN 加速。
 *
 * 与 /api/gh/ 的区别：
 *   - /api/gh/    → 反代 github.com（下载 Release 资产，二进制流）
 *   - /api/gh-api → 反代 api.github.com（JSON API，小体积）
 *
 * 为什么用 _middleware.ts 而不是 [[...path]].ts：
 *   Cloudflare Pages Functions 不支持 [[...name]] 这种带 "..." 的 catch-all 语法，
 *   参数名只能包含字母数字和下划线。
 *   _middleware.ts 是官方推荐的 catch-all 方案，会匹配该目录及所有子路径。
 *
 * 免费额度：Cloudflare Pages Functions 每日 10 万次调用。
 */

interface Env {
  // 可选：GitHub Personal Access Token，提高 API 速率限制（未设置时走匿名 60 次/小时/IP）
  // 在 Cloudflare Pages 项目设置 → Environment variables 添加 GITHUB_TOKEN
  GITHUB_TOKEN?: string;
}

interface PagesFunctionContext<E = unknown> {
  request: Request;
  env: E;
  params: Record<string, string | string[] | undefined>;
  waitUntil: (promise: Promise<unknown>) => void;
  next: () => Promise<Response>;
}

const GITHUB_API_HOST = 'api.github.com';

// 允许透传给 GitHub API 的请求头白名单
const ALLOWED_REQUEST_HEADERS = new Set([
  'accept',
  'accept-encoding',
  'accept-language',
  'if-none-match', // ETag 条件请求，减少速率限制消耗
  'if-modified-since',
  'user-agent',
]);

// 允许回传给客户端的响应头白名单
const ALLOWED_RESPONSE_HEADERS = new Set([
  'content-type',
  'content-length',
  'content-encoding',
  'etag',
  'last-modified',
  'cache-control',
  'expires',
  'x-ratelimit-limit',
  'x-ratelimit-remaining',
  'x-ratelimit-reset',
]);

function jsonError(message: string, status = 400): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}

export const onRequest = async (context: PagesFunctionContext<Env>): Promise<Response> => {
  const { request, env } = context;
  const url = new URL(request.url);

  // 仅允许 GET / HEAD
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return jsonError('Method Not Allowed', 405);
  }

  // 提取路径：/api/gh-api/<path...> → <path...>
  const path = url.pathname.replace(/^\/api\/gh-api\//, '');
  if (!path) {
    return jsonError('Missing path. Usage: /api/gh-api/repos/<owner>/<repo>/releases');
  }

  // 仅允许 /repos/ 开头的路径（防止被滥用为开放 API 代理）
  if (!path.startsWith('repos/')) {
    return jsonError('Only /repos/* paths are allowed', 403);
  }

  const targetUrl = `https://${GITHUB_API_HOST}/${path}${url.search}`;

  // 构造请求头
  const upstreamHeaders = new Headers();
  for (const key of ALLOWED_REQUEST_HEADERS) {
    const value = request.headers.get(key);
    if (value) upstreamHeaders.set(key, value);
  }
  // GitHub API 要求 User-Agent
  if (!upstreamHeaders.has('user-agent')) {
    upstreamHeaders.set('user-agent', 'Lumio-Mirror/1.0 (+https://xksye7.dpdns.org)');
  }
  // GitHub API 强烈建议 Accept JSON
  if (!upstreamHeaders.has('accept')) {
    upstreamHeaders.set('accept', 'application/vnd.github+json');
  }
  // 可选：配置 GITHUB_TOKEN 提高速率限制（从 60 → 5000 次/小时）
  if (env.GITHUB_TOKEN) {
    upstreamHeaders.set('authorization', `Bearer ${env.GITHUB_TOKEN}`);
  }

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers: upstreamHeaders,
      redirect: 'follow',
    });
  } catch (err) {
    return jsonError(`Upstream fetch failed: ${(err as Error).message}`, 502);
  }

  // 构造响应头
  const responseHeaders = new Headers();
  for (const key of ALLOWED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(key);
    if (value) responseHeaders.set(key, value);
  }
  responseHeaders.set('access-control-allow-origin', '*');
  // 缓存 10 分钟（GitHub Releases 更新频率低，减少 API 调用）
  // 注意：仅对成功的 200 响应缓存，304/4xx/5xx 不缓存
  if (upstream.status === 200) {
    responseHeaders.set('cache-control', 'public, max-age=600, s-maxage=600');
  }

  // HEAD 请求不返回 body
  const body = request.method === 'HEAD' ? null : upstream.body;

  return new Response(body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
};
