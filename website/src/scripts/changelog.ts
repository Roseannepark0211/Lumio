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
 *  ⚠️  Fallback 数据 — 网络失败时兜底
 *  保持最新 3 个版本，发版时同步更新此数组
 *  数据来源：GitHub Releases API（https://api.github.com/repos/Roseannepark0211/Lumio/releases）
 * ============================================================================ */
export const FALLBACK_RELEASES: ParsedRelease[] = [
  {
    version: '4.4.2',
    date: '2026-07-29',
    sections: [
      {
        title: '✨ 新功能',
        items: [
          '[插件 ext-v4.4.6] IG carousel（多图帖子）自动翻页提取完整图片：模拟点击"下一张"按钮逐张翻页去重合并，突破 IG DOM 仅渲染当前+相邻 slide（约 4 张）的限制 [API 行为变更]',
          '[主程序 V4.4.2] Inbox 状态随下载任务终态自动同步：完成→downloaded、失败→failed、取消→new（可重新下载），通过 task_id↔inbox_item_id 映射在 task_status_changed 回调中更新 [API 行为变更]',
        ],
      },
      {
        title: '🐛 Bug 修复',
        items: [
          '[主程序] 修复素材文件缺失时弹出多次删除确认对话框：MediaPreviewDialog 移除内嵌删除按钮与 isFileMissing 状态，由 LibraryPage 通过 listPreviewItems 预检查 + 后端 file_missing 事件统一弹一次确认',
          '[主程序] 修复托盘菜单频繁重连导致"连接中…"闪烁：WS 已连接时仅刷新 queue/inbox 业务数据，未连接才调 loadAll 重建连接',
          '[主程序] 修复 TS 编译失败：移除 MediaPreviewDialog 中未使用的 isFileMissing 字段与 onDeleteMissingRecord 方法',
          '[插件 ext-v4.4.5] 修复右键菜单对抖音 modal_id 模式、m.weibo.cn、weibo.com/detail/{id} 误判为非详情页导致不触发元数据提取：改用 shared/detailPage.ts 统一判定',
        ],
      },
      {
        title: '🔨 重构（插件）',
        items: [
          '[插件 ext-v4.4.6] 移除诊断采集工具：删除 shared/diagnose.ts（1402 行）+ SettingsGear.tsx 诊断 UI（164 行）+ content/index.ts 消息处理，累计减少约 1583 行代码',
          '[插件 ext-v4.4.5] 共享代码去重：将 contextMenus.ts 的 isDetailPageUrl / platformLabel 提取到 shared/（platformLabels.ts + detailPage.ts），消除 background 与 popup 之间重复维护的映射表',
          '[插件 ext-v4.4.5] IG 提取器路径规范化：ig_extract.ts → platforms/instagram.ts，统一 platforms/ 目录命名',
          '[插件 ext-v4.4.5] tsconfig 清理：composite 模式仅为 vite.config.ts / manifest.config.ts 生成 .d.ts，移除 scripts 目录引用',
          '[插件 ext-v4.4.6] 微博提取代码注释脱敏：真实 uid/post_id 替换为 {uid}/{post_id} 占位符',
        ],
      },
      {
        title: '⚠️ 已知问题',
        items: ['（无）'],
      },
      {
        title: '📦 安装说明',
        items: [
          '主程序：V4.4.1 → V4.4.2，electron-builder 输出目录改为 release4',
          '浏览器扩展：ext-v4.4.0 → ext-v4.4.6，版本号独立，重新加载插件即可',
          '升级建议：IG 多图帖子用户请优先更新插件以获得完整 carousel 提取能力',
        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.4.2',
  },
  {
    version: '4.4.1',
    date: '2026-07-29',
    sections: [
      {
        title: '🐛 修复内容',
        items: [
          '修复 YouTube 视频已存在时下载队列卡在"合并中"的 bug：glob(f"{stem}.*") 用 fnmatch 模式匹配，方括号 [4K]/[1080p] 被解释为字符集；改用 iterdir() + startswith() 做字面量匹配，覆盖 4 处下载路径；修复 skip 策略分支未设置 task.filename 导致 on_done 判定失败无限重试',
          '修复托盘右键菜单偶发"未连接"状态：fetch 添加 AbortController 4 秒超时；重试次数 3 次/1.5s 改为 8 次/1s（覆盖 FastAPI 冷启动 10s+）；先用 /api/health 探活再拉业务数据；tray:reload 立即显示"加载中"；菜单隐藏时停止轮询和重试定时器',
          '修复主页粘贴按钮无法读取剪贴板（迁移架构时引入）：64 位 Windows 上 ctypes 默认 restype=c_int（32 位），GetClipboardData/GlobalLock 返回 64 位指针被截断 → 访问违例 0xC0000005 崩溃；显式设置 restype=wintypes.HANDLE/LPVOID，添加 GlobalLock/GlobalUnlock 配对；添加 OpenClipboard 失败重试',
          '修复 CI 测试失败：TaskStatus 枚举测试同步新增 MERGING/PARSING 状态',
        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.4.1',
  },
  {
    version: '4.4.0',
    date: '2026-07-28',
    sections: [
      {
        title: '✨ 新功能',
        items: [
          '架构迁移完成：从 QML 单体架构完整迁移至 Electron + React + FastAPI 双进程架构，前端 8 个页面全部 React 化',
          'Liquid Glass 设计语言：3D 字标 + 蓝青色主题 + 柔和光球 + 大圆角',
          '系统托盘菜单 + 关闭确认弹窗（最小化/退出/取消）',
          '内置媒体预览对话框：图片缩放/平移/多图切换 + 视频/音频播放器',
          '小红书 Live Photo 支持：实况图返回图片+视频双项',
          'Collection 智能操作 + 右键菜单支持重命名/删除',
          '前端 i18n 双语：全页面接入中英即时切换',
          '自动更新机制：electron-updater + UpdateDialog 弹窗',
          'CI/CD 自动发布：GitHub Actions 三平台矩阵构建',
          '跨平台原生安装包：Windows NSIS + macOS DMG（x64/arm64）+ Linux AppImage/deb/rpm',
        ],
      },
      {
        title: '⚡ 性能优化',
        items: [
          '启动速度：splash 秒开 + FastAPI spawn 前移 + React 页面延迟到 FastAPI ready 后加载',
          '安装包体积：compression: "maximum" + asar: true，从 ~600MB 降至 ~140MB',
          '虚拟列表：react-window 长列表虚拟滚动',
          'WebSocket 增量更新：避免全量轮询',
        ],
      },
      {
        title: '⚠️ 已知问题',
        items: [
          '抖音超高清原画档位（60帧 H.265）仍需 app API 或登录态，web API 无法获取',
          'X GraphQL API query ID 会定期轮换，422 报错时需从 yt-dlp 源码更新硬编码',
        ],
      },
    ],
    url: 'https://github.com/Roseannepark0211/Lumio/releases/tag/v4.4.0',
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
