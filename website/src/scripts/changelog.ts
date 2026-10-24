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

// GitHub API — Releases 列表
// 文档：https://docs.github.com/en/rest/releases/releases#list-releases
//
// ⚠️ 国内访问优化：
//   原直连 https://api.github.com 在国内不稳定，部分网络无法直连。
//   现改走自建 Cloudflare Pages Function 反代 /api/gh-api/，
//   走 Cloudflare CDN 加速，国内无需代理即可获取真实更新日志。
//   反代代码：functions/api/gh-api/[[...path]].ts
//
//   dev 模式（import.meta.env.DEV）下 Pages Function 不可用，仍走直连。
const GITHUB_API_DIRECT = 'https://api.github.com/repos/Roseannepark0211/Lumio/releases?per_page=8';
const GITHUB_API_MIRROR = '/api/gh-api/repos/Roseannepark0211/Lumio/releases?per_page=8';

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
 *  摘要模式 — 每个版本最多显示 SUMMARY_MAX_ITEMS 条，超出折叠
 *  超出部分点击「查看完整 Release」跳转 GitHub
 *  让官网日志保持简短，避免与 GitHub Release 页面重复
 * ============================================================================ */
export const SUMMARY_MAX_ITEMS = 3;

export interface ChangelogSummary {
  sections: ChangelogSection[];
  hasMore: boolean; // 是否有被截断的内容
  totalItems: number;
}

/**
 * 将完整 release sections 转为摘要（最多 N 条 items）
 *
 * 截断策略：
 *   - 优先保留前几个 section 的前几条 items
 *   - 跨 section 累计，达到上限后丢弃剩余
 *   - hasMore = true 时显示「查看完整 Release」链接
 */
export function toSummary(release: { sections: ChangelogSection[] }): ChangelogSummary {
  const result: ChangelogSection[] = [];
  let count = 0;
  let totalItems = 0;
  let hasMore = false;

  // 先统计总条数
  for (const section of release.sections) {
    totalItems += section.items.length;
  }

  for (const section of release.sections) {
    if (count >= SUMMARY_MAX_ITEMS) {
      hasMore = true;
      break;
    }
    const remaining = SUMMARY_MAX_ITEMS - count;
    const items = section.items.slice(0, remaining);
    if (items.length < section.items.length) {
      hasMore = true;
    }
    if (items.length > 0) {
      result.push({ title: section.title, items });
      count += items.length;
    }
  }

  return {
    sections: result,
    hasMore: hasMore || totalItems > SUMMARY_MAX_ITEMS,
    totalItems,
  };
}

/* ============================================================================
 *  ⚠️  Fallback 数据 — 网络失败时兜底
 *  保持最新 3 个版本，发版时同步更新此数组
 *  数据来源：GitHub Releases API（https://api.github.com/repos/Roseannepark0211/Lumio/releases）
 * ============================================================================ */
export const FALLBACK_RELEASES: ParsedRelease[] = [
  {
    version: '4.5.2',
    date: '2026-10-24',
    sections: [
      {
        title: '📥 普通用户下载（只需选一个）',
        items: [

        ],
      },
      {
        title: '📋 更新内容',
        items: [
          '打包版抖音解析恢复：安装包补上浏览器组件与驱动，优先复用本机 Chrome/Edge，不用再下载 Chromium（修复 v4.5.1 安装包里浏览器兜底不可用的问题）',
          '未找到可用浏览器时给出明确提示：请安装 Chrome 或 Edge 后重试，或运行 playwright install chromium',
          '修复发版后官网版本同步失败的问题',
        ],
      },
      {
        title: '💻 系统要求',
        items: [
          '**Windows**: Windows 10/11 x64',
          '**macOS**: macOS 12+（仅 Apple Silicon，Intel Mac 暂不提供预编译包）',
          '**Linux**: Ubuntu 20.04+ / Fedora 36+ / Debian 11+ x64',
        ],
      },
      {
        title: '📦 安装说明',
        items: [

        ],
      },
      {
        title: '🔄 自动更新',
        items: [
          '**Windows / Linux**: 检测到新版本后弹窗提示，确认后后台下载，完成后一键重启安装',
          '**macOS**: 检测到新版本后跳转到 Release 页面手动下载 DMG（无 Apple Developer 证书，不支持自动更新）',
        ],
      },
      {
        title: '🛠️ 从源码运行（开发者）',
        items: [

        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.5.2',
  },
  {
    version: '4.5.1',
    date: '2026-10-24',
    sections: [
      {
        title: '📥 普通用户下载（只需选一个）',
        items: [

        ],
      },
      {
        title: '📋 更新内容',
        items: [
          '抖音解析恢复：Argus 升级后无签名请求被拦截，新增浏览器拦截兜底（视频优先走 www 页，图文走分享页），多清晰度与图文均已验证',
          '更新检查报错提示改为中文友好文案，并附原始错误详情与重试、官网下载入口',
          '关闭弹窗的“记住”只对应最小化与退出，点取消不再残留状态',
        ],
      },
      {
        title: '💻 系统要求',
        items: [
          '**Windows**: Windows 10/11 x64',
          '**macOS**: macOS 12+（仅 Apple Silicon，Intel Mac 暂不提供预编译包）',
          '**Linux**: Ubuntu 20.04+ / Fedora 36+ / Debian 11+ x64',
        ],
      },
      {
        title: '📦 安装说明',
        items: [

        ],
      },
      {
        title: '🔄 自动更新',
        items: [
          '**Windows / Linux**: 检测到新版本后弹窗提示，确认后后台下载，完成后一键重启安装',
          '**macOS**: 检测到新版本后跳转到 Release 页面手动下载 DMG（无 Apple Developer 证书，不支持自动更新）',
        ],
      },
      {
        title: '🛠️ 从源码运行（开发者）',
        items: [

        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.5.1',
  },
  {
    version: '4.5.0',
    date: '2026-10-13',
    sections: [
      {
        title: '🏗️ 架构迁移',
        items: [
          '完成数据模型统一：旧 VideoInfo 模型彻底删除，全链路统一使用 MediaInfo',
          '移除新旧模型间的桥接转换代码，解析→入队→下载链路更直接',
          '删除无调用的死代码 _build_format_options',
        ],
      },
      {
        title: '🖼️ 素材库修复',
        items: [
          '修复缩略图工作线程的信号冲突，视频缩略图异步生成恢复正常',
          '删除素材时可选择同时删除磁盘文件',
          '新增素材库搜索 API（关键词/平台/类型/收藏/合集/日期/批次）',
          'CDN 链接去重（忽略易过期的签名参数）',
        ],
      },
      {
        title: '✨ 体验与稳定性',
        items: [
          'Instagram 解析失败时提示导入 Cookie 或使用浏览器插件',
          '粘贴链接任务默认自动开始下载（可关闭）',
          '粘贴任务支持指定输出目录',
          '链接解析支持同步等待模式，命令行支持 --host/--port/--token 参数',
        ],
      },
      {
        title: '🧹 清理',
        items: [
          '移除无用依赖 instaloader',
          '明确浏览器插件伴随服务的固定端口设计（非迁移残留）',
          '修复测试间 provider 注册表互相污染的问题',
        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.5.0',
  },
];

/**
 * 从 GitHub API 拉取 releases
 * 失败时返回 null（由调用方走 fallback）
 *
 * 策略：
 *   - 生产环境：走 /api/gh-api/ 镜像（Cloudflare CDN 加速，国内无需代理）
 *   - 开发环境：直连 api.github.com（dev server 不支持 Pages Function）
 *   - 失败时：返回 null，调用方走 FALLBACK_RELEASES
 */
export async function fetchReleases(): Promise<ParsedRelease[] | null> {
  const apiUrl = import.meta.env.DEV ? GITHUB_API_DIRECT : GITHUB_API_MIRROR;
  try {
    const res = await fetch(apiUrl, {
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
 * 也支持纯文本标题行（无 ## 前缀但独占一行）：
 *   ✨ 新功能
 *   [插件] xxx
 *   [主程序] yyy
 *   🐛 Bug 修复
 *   - 修复1
 *
 * 判定规则：以 emoji 开头 / 匹配常见标题关键词 → 视为 section 标题
 */
const SECTION_TITLE_KEYWORDS = [
  '新功能', 'Bug 修复', '修复内容', '重构', '性能优化', '架构迁移',
  '已知问题', '安装说明', 'Breaking', '破坏性变更', '其他',
  'New Features', 'Bug Fixes', 'Refactor', 'Performance', 'Breaking Changes',
  'Known Issues', 'Installation', 'Others',
];

function isSectionTitle(line: string): boolean {
  // ## 标题
  if (/^#{1,6}\s+/.test(line)) return true;
  // 以 emoji 开头（✨🐛⚡🏗️⚠️📦🔥🚀等）
  if (/^[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(line)) return true;
  // 匹配常见标题关键词（整行就是标题词）
  return SECTION_TITLE_KEYWORDS.some((kw) => line === kw || line.startsWith(kw));
}

export function parseBody(body: string): ChangelogSection[] {
  if (!body) return [];

  const lines = body.split(/\r?\n/);
  const sections: ChangelogSection[] = [];
  let current: ChangelogSection | null = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    // 跳过纯 release 标题行（如 "release: V4.4.1"）
    if (/^release:\s*v?\d/i.test(line) && lines.length > 1) continue;

    // 标题行（## 标题 / emoji 开头 / 关键词匹配）
    if (isSectionTitle(line)) {
      // 去掉 ## 前缀
      const title = line.replace(/^#{1,6}\s+/, '').trim();
      if (current && current.items.length > 0) sections.push(current);
      current = { title, items: [] };
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
    current.items.push(line);
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
