/**
 * Cloudflare Pages Function — GitHub Release 下载反代（中间件版）
 *
 * 路径格式：
 *   /api/gh/<owner>/<repo>/releases/download/<tag>/<file>
 *   /api/gh/<owner>/<repo>/archive/<ref>.zip
 *
 * 示例：
 *   /api/gh/Roseannepark0211/Lumio/releases/download/v4.4.2/Lumio-Setup-4.4.2.exe
 *   → 代理 https://github.com/Roseannepark0211/Lumio/releases/download/v4.4.2/Lumio-Setup-4.4.2.exe
 *
 * 工作原理：
 *   1. 接收客户端请求 → 拼接成 https://github.com/<path>
 *   2. 用 fetch(redirect: 'follow') 跟随 302 到 objects.githubusercontent.com
 *   3. 流式回传响应（支持大文件，100MB+ 安装包无压力）
 *   4. 客户端只与 Cloudflare CDN 通信，不直连 GitHub
 *
 * 为什么用 _middleware.ts 而不是 [[...path]].ts：
 *   Cloudflare Pages Functions 不支持 [[...name]] 这种带 "..." 的 catch-all 语法，
 *   参数名只能包含字母数字和下划线。
 *   _middleware.ts 是官方推荐的 catch-all 方案，会匹配该目录及所有子路径。
 *
 * 安全限制：
 *   - 仅代理 github.com（防止被滥用为开放代理）
 *   - 仅允许 GET / HEAD 方法
 *   - 限制请求头透传，避免泄露 cookie
 *
 * 免费额度：Cloudflare Pages Functions 每日 10 万次调用，个人项目足够。
 */

interface Env {
  // 如需未来扩展（如鉴权 token），可在此声明
}

interface PagesFunctionContext<E = unknown> {
  request: Request;
  env: E;
  params: Record<string, string | string[] | undefined>;
  waitUntil: (promise: Promise<unknown>) => void;
  next: () => Promise<Response>;
}

const GITHUB_HOST = 'github.com';

// 允许透传给 GitHub 的请求头白名单
const ALLOWED_REQUEST_HEADERS = new Set([
  'accept',
  'accept-encoding',
  'accept-language',
  'range', // 断点续传
  'user-agent',
]);

// 允许回传给客户端的响应头白名单
const ALLOWED_RESPONSE_HEADERS = new Set([
  'content-type',
  'content-length',
  'content-disposition',
  'content-encoding',
  'content-range',
  'accept-ranges',
  'etag',
  'last-modified',
  'cache-control',
  'expires',
]);

function forbidden(message: string, status = 403): Response {
  return new Response(message, {
    status,
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  });
}

export const onRequest = async (context: PagesFunctionContext<Env>): Promise<Response> => {
  const { request } = context;
  const url = new URL(request.url);

  // 仅允许 GET / HEAD（下载场景不需要 POST 等）
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return forbidden('Method Not Allowed', 405);
  }

  // 提取路径：/api/gh/<path...> → <path...>
  const path = url.pathname.replace(/^\/api\/gh\//, '');
  if (!path) {
    return forbidden('Missing path. Usage: /api/gh/<owner>/<repo>/releases/download/...');
  }

  // 拼接目标 URL（保留 query string，部分 GitHub 链接带参数）
  const targetUrl = `https://${GITHUB_HOST}/${path}${url.search}`;

  // 构造干净的请求头（仅透传白名单）
  const upstreamHeaders = new Headers();
  for (const key of ALLOWED_REQUEST_HEADERS) {
    const value = request.headers.get(key);
    if (value) upstreamHeaders.set(key, value);
  }
  // 设置合理的 User-Agent（GitHub 要求 UA，否则可能 403）
  if (!upstreamHeaders.has('user-agent')) {
    upstreamHeaders.set('user-agent', 'Lumio-Mirror/1.0 (+https://xksye7.dpdns.org)');
  }

  // 发起上游请求 — follow redirect 自动跟随 302 到 objects.githubusercontent.com
  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers: upstreamHeaders,
      redirect: 'follow',
    });
  } catch (err) {
    return forbidden(`Upstream fetch failed: ${(err as Error).message}`, 502);
  }

  // 上游返回非 2xx/3xx 时直接透传错误（避免掩盖 GitHub 的 404/403）
  if (!upstream.ok) {
    return new Response(`GitHub returned ${upstream.status}`, {
      status: upstream.status,
      headers: { 'content-type': 'text/plain; charset=utf-8' },
    });
  }

  // 构造干净的响应头（仅透传白名单）
  const responseHeaders = new Headers();
  for (const key of ALLOWED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(key);
    if (value) responseHeaders.set(key, value);
  }
  // 允许跨域（虽然下载场景一般用不到，但加上无害）
  responseHeaders.set('access-control-allow-origin', '*');
  // 隐藏上游真实来源
  responseHeaders.delete('server');
  responseHeaders.delete('via');

  // 流式回传响应体（支持大文件，零内存缓冲）
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
};
