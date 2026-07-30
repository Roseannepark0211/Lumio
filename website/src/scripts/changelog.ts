/**
 * changelog.ts — 更新日志数据层
 *
 * 策略：
 *   1. 优先 fetch GitHub Releases API（自动获取最新版本）
 *   2. fetch 失败 / 网络不可达 / 限流 → 使用 FALLBACK_RELEASES 兜底
 *   3. markdown body 解析为 sections（## 标题 + - 列表）
 *
 * 数据流：fetchReleases → parseBody → 渲染
 */

import type { ReleaseInfo } from './types';

const GITHUB_API = 'https://api.github.com/repos/Roseannepark0211/Lumio/releases?per_page=8';

/** 解析后的 section 结构 */
export interface ChangelogSection {
  title: string;
  items: string[];
}

/** 解析后的 release 结构 — 给前端渲染用 */
export interface ParsedRelease {
  version: string;
  date: string;
  sections: ChangelogSection[];
  url: string;
}

/* ============================================================================
 *  ⚠️  Fallback 数据 — 网络失败时兜底
 *  保持最新 5 个版本，发版时同步更新此数组
 * ============================================================================ */
export const FALLBACK_RELEASES: ParsedRelease[] = [
  {
    version: '4.4.2',
    date: '2026-07-25',
    sections: [
      {
        title: '✨ 新功能',
        items: [
          '浏览器扩展支持微博平台',
          '下载弹窗支持 macOS / Linux',
          '抖音清晰度选择独立于格式选择',
        ],
      },
      {
        title: '🐛 Bug 修复',
        items: [
          '修复抖音封面被裁剪问题',
          '修复 inbox 状态同步问题',
          '修复托盘频繁重连问题',
        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.4.2',
  },
  {
    version: '4.4.0',
    date: '2026-07-15',
    sections: [
      {
        title: '✨ 新功能',
        items: [
          '抖音 Provider 重构，支持图文帖',
          '小红书 HTML 抓取替代旧 API',
          '微博 livephoto 完整支持',
          '浏览器扩展 Manifest V3 重写',
        ],
      },
      {
        title: '⚡ 性能优化',
        items: [
          'Provider 缓存两级（内存+文件）',
          '缩略图异步生成不阻塞启动',
          '队列原子写入防崩溃截断',
        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.4.0',
  },
  {
    version: '4.3.0',
    date: '2026-06-20',
    sections: [
      {
        title: '✨ 新功能',
        items: [
          'QML 主界面 V4.3 重构',
          '8 平台统一 Provider 架构',
          'Collections 分类系统',
          '全文搜索 + 多维筛选',
        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.3.0',
  },
];

/**
 * 从 GitHub API 拉取 releases
 * 失败时返回 null（由调用方走 fallback）
 */
export async function fetchReleases(): Promise<ParsedRelease[] | null> {
  try {
    const res = await fetch(GITHUB_API, {
      headers: {
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    });

    if (!res.ok) {
      console.warn(`[Changelog] GitHub API returned ${res.status}`);
      return null;
    }

    const data = (await res.json()) as ReleaseInfo[];
    if (!Array.isArray(data) || data.length === 0) return null;

    return data
      .filter((r) => !r.draft && !r.prerelease)
      .slice(0, 5)
      .map(parseRelease);
  } catch (err) {
    console.warn('[Changelog] fetch failed:', err);
    return null;
  }
}

/** 将 GitHub Release 解析为前端可渲染结构 */
function parseRelease(r: ReleaseInfo): ParsedRelease {
  // tag_name: "v4.4.2" → "4.4.2"
  const version = r.tag_name.replace(/^v/i, '');
  const date = r.published_at ? r.published_at.slice(0, 10) : '';
  const sections = parseBody(r.body || '');

  return {
    version,
    date,
    sections: sections.length > 0 ? sections : [{ title: '更新内容', items: [r.name || version] }],
    url: r.html_url,
  };
}

/**
 * 解析 release body markdown
 *
 * 支持格式：
 *   ## ✨ 新功能
 *   - 功能1
 *   - 功能2
 *
 *   ## 🐛 Bug 修复
 *   - 修复1
 *
 * 不支持的格式（如纯文本无 ## 标题）→ 归入「更新内容」section
 */
export function parseBody(body: string): ChangelogSection[] {
  if (!body) return [];

  const lines = body.split(/\r?\n/);
  const sections: ChangelogSection[] = [];
  let current: ChangelogSection | null = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    // ## 标题
    const h2 = line.match(/^##\s+(.+)$/);
    if (h2) {
      if (current && current.items.length > 0) sections.push(current);
      current = { title: h2[1].trim(), items: [] };
      continue;
    }

    // - 列表项 / * 列表项
    const li = line.match(/^[-*]\s+(.+)$/);
    if (li && current) {
      current.items.push(li[1].trim());
      continue;
    }

    // 普通文本行 — 若当前无 section，新建一个「更新内容」
    if (!current) {
      current = { title: '更新内容', items: [] };
    }
    // 普通段落文本也加入 items（保留信息）
    if (!line.match(/^#{1,6}\s/)) {
      current.items.push(line);
    }
  }

  if (current && current.items.length > 0) sections.push(current);
  return sections;
}

/** 格式化日期 — "2026-07-25" → "2026 年 7 月 25 日" */
export function formatDate(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`;
}

/** 解析行内格式：**加粗** / `code` / [link](url) */
export function parseInline(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener" class="faq-link">$1</a>'
  );
  return html;
}

/** 获取 releases — 自动获取失败时回退到 fallback */
export async function getReleases(): Promise<ParsedRelease[]> {
  const remote = await fetchReleases();
  if (remote && remote.length > 0) return remote;
  return FALLBACK_RELEASES;
}
