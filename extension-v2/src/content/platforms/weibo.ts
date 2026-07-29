/**
 * 微博元数据提取
 *
 * ★ 关键澄清：微博没有传统"详情页"，博主主页是流式帖子列表
 *   - 博主主页 URL：https://weibo.com/u/{uid}（或自定义昵称 weibo.com/{name}）
 *   - 单帖子 URL：https://weibo.com/{uid}/{post_id}（少见，从外部跳转进来）
 *
 * ★ 诊断数据确认的 DOM 结构（PC 版 weibo.com，2026-07-29）：
 *   div.wbpro-scroller-item             ← 流式列表项（稳定 class）
 *     article._wrap_ecgcn_2              ← 帖子卡片
 *       div._body_ecgcn_63               ← 帖子主体（含 header + content）
 *         header.woo-box-flex            ← 帖子头部
 *           a[href*='/u/'][aria-label]   ← 头像/作者链接
 *           a span[title]                ← 作者名
 *           a[href*='weibo.com/{uid}/{post_id}']  ← ★ 帖子 URL（在时间链接上）
 *         div.wbpro-feed-content         ← 帖子内容
 *           div._wbtext_1h76l_19         ← 正文
 *           div.picture                  ← 图片容器（图片帖子）
 *           [video 元素]                 ← 视频容器（视频帖子）
 *
 * ★ 帖子 URL 提取关键：
 *   header 内有多个 a[href*='weibo.com/']：
 *   - 头像/作者名链接：weibo.com/u/{uid}（有 /u/）
 *   - 时间链接：weibo.com/{uid}/{post_id}（无 /u/，这才是帖子 URL）
 *   用正则 /weibo\.com\/\d+\/[a-zA-Z0-9]+/ 匹配（排除 /u/ 路径）
 *
 * ★ 策略：
 *   1. 博主主页 + 右键某帖子图片/video → 从右键元素向上找 wbpro-scroller-item
 *      → 提取该帖子 URL → 发送给后端解析（含最高画质选择）
 *   2. 博主主页 + popup 主动调用 → 返回博主信息（type: "profile" 触发批量）
 *   3. 单帖子 URL → 提取 og + DOM 元数据
 *
 * ★ 不提取 direct_url：微博视频 src 是 blob:，sinaimg.cn 图片需 Cookie，
 *   浏览器侧无法可靠直链下载。交给后端 WeiboProvider 调 API 拿最高画质。
 */
import { commonOg } from "../shared/og";
import type { ExtractResult } from "../shared/types";

// ── 右键上下文：双轨制记录右键元素位置 ────────────────
//
// ★ 核心问题：MV3 Service Worker 在右键菜单展开期间可能被 Chrome 回收，
//   background 调 extractNow 时若 content script 未响应（SW 重启），
//   background 会手动注入新的 content script bundle，
//   新实例的模块级变量是空的，_lastContextMenuTarget 丢失。
//
// ★ 双轨制方案（attribute 主 + storage.session 辅）：
//
//   1. ★ 主机制：document attribute
//      - contextmenu 事件给元素打 data-lumio-ctx-target="<timestamp>" 属性
//      - 旧元素先清除标记，确保同一时刻只有 1 个 ctxTarget
//      - 跨 content script 实例可用（document.body 是 DOM，所有 world 共享）
//      - 元素跟随 DOM 变化（即使帖子被重新渲染，attribute 仍在元素上）
//      - 不依赖 selector path，不会因 DOM 结构变化失效
//
//   2. ★ 辅机制：chrome.storage.session + selector path
//      - setContextMenuTarget 同时存 path + ts 到 storage.session
//      - 场景：右键元素被虚拟滚动卸载（attribute 跟随元素消失）
//        但 path 可能定位到新 DOM 中类似位置的元素（不完美但比 null 好）
//
// ★ 过期机制：30 秒内有效
//   场景：用户右键图片 → Chrome 显示菜单 → 浏览菜单后点击 → 触发 extractNow
//   Chrome 右键菜单从展开到用户点击可能耗时 5-10 秒（用户在阅读菜单项）
//   30 秒足够覆盖"右键 → 阅读 → 点击"全过程
//   ★ popup 主动打开时若 >30 秒已过，自动走"返回博主信息"分支

const CONTEXT_TARGET_TTL_MS = 30000;
const STORAGE_KEY = "weibo_context_target";
/** 在右键元素上打的 attribute 名（值是 timestamp，便于过期判断） */
const CTX_TARGET_ATTR = "data-lumio-ctx-target";

interface StoredContextTarget {
  /** CSS selector path（:nth-of-type 链） */
  path: string;
  /** 右键时间戳 */
  ts: number;
  /** 元素 tag + class（便于日志追溯） */
  tag: string;
  className: string;
}

/**
 * 为元素构造从 body 到该元素的 selector path
 *
 * ★ 策略：向上遍历，每层用 tag:nth-of-type(n)
 *   - 不用 id（微博动态生成，不稳定）
 *   - 不用 class（class 含 hash，每次发版变化）
 *   - 用 :nth-of-type(n) 表示"该层第 n 个该 tag 元素"
 *
 * ★ 性能：帖子元素深度通常 5-8 层，path 长度可控
 */
function buildSelectorPath(el: Element): string {
  const parts: string[] = [];
  let current: Element | null = el;
  while (current && current !== document.body) {
    const parent: Element | null = current.parentElement;
    if (!parent) break;
    // 计算当前元素是父元素下第几个同类 tag
    const tag = current.tagName.toLowerCase();
    let nth = 1;
    let sibling: Element | null = current.previousElementSibling;
    while (sibling) {
      if (sibling.tagName.toLowerCase() === tag) nth++;
      sibling = sibling.previousElementSibling;
    }
    parts.unshift(`${tag}:nth-of-type(${nth})`);
    current = parent;
  }
  // 从 body 开始
  return "body > " + parts.join(" > ");
}

/**
 * 用 selector path 重新定位元素
 * path 失效时返回 null（DOM 已变化）
 */
function querySelectorByPath(path: string): Element | null {
  try {
    return document.querySelector(path);
  } catch {
    return null;
  }
}

/**
 * 记录右键元素（content script 的 contextmenu 事件监听器调用）
 *
 * ★ 双轨制：
 *   1. 主机制：在元素上打 data-lumio-ctx-target="<timestamp>" attribute
 *      跨 content script 实例可用（DOM 共享），元素跟随 DOM 变化
 *   2. 辅机制：存 path + ts 到 chrome.storage.session
 *      用于右键元素被卸载时 fallback 定位
 *
 * ★ 旧标记清除：同一时刻只保留 1 个 ctxTarget
 *   避免多次右键产生多个 attribute 标记混淆定位
 */
export async function setContextMenuTarget(el: Element | null): Promise<void> {
  // 先清除旧 attribute 标记（无论 el 是否为 null）
  const oldMarked = document.querySelector(`[${CTX_TARGET_ATTR}]`);
  if (oldMarked) {
    oldMarked.removeAttribute(CTX_TARGET_ATTR);
  }

  if (!el) {
    try {
      await chrome.storage.session.remove(STORAGE_KEY);
    } catch {
      // ignore
    }
    return;
  }

  // ★ 主机制：在元素上打 attribute（带 timestamp，便于过期判断）
  const ts = Date.now();
  el.setAttribute(CTX_TARGET_ATTR, ts.toString());
  console.log(
    `[Lumio-weibo] setContextMenuTarget: 已标记 <${el.tagName.toLowerCase()}>` +
      `(class=${(el.className || "").slice(0, 50)})`,
  );

  // ★ 辅机制：存 path + ts 到 storage.session（冗余备份）
  const path = buildSelectorPath(el);
  const stored: StoredContextTarget = {
    path,
    ts,
    tag: el.tagName,
    className: (el.className || "").slice(0, 80),
  };
  try {
    await chrome.storage.session.set({ [STORAGE_KEY]: stored });
  } catch (e) {
    console.log(`[Lumio-weibo] setContextMenuTarget: storage 写入失败（attribute 主机制仍可用）`, e);
  }
}

/**
 * 读取右键元素（extractWeibo 调用）
 *
 * ★ 优先级：
 *   1. document attribute（主）：跨 content script 实例可用，跟随元素移动
 *   2. chrome.storage.session + selector path（辅）：元素被卸载时 fallback
 *
 * ★ 过期机制：30s TTL
 * ★ 消费后不删除：允许同一右键被多次 extractNow 调用（如 SW 重启后重试）
 */
async function getFreshContextMenuTarget(): Promise<Element | null> {
  // ── 主机制：document attribute ─────────────────────────────
  const attrEl = document.querySelector(`[${CTX_TARGET_ATTR}]`);
  if (attrEl) {
    const tsStr = attrEl.getAttribute(CTX_TARGET_ATTR) || "0";
    const ts = parseInt(tsStr, 10);
    const age = Date.now() - ts;
    if (age <= CONTEXT_TARGET_TTL_MS) {
      console.log(
        `[Lumio-weibo] ctxTarget (attr): 有 <${attrEl.tagName.toLowerCase()}>` +
          `(${Math.floor(age / 1000)}s 前)`,
      );
      return attrEl;
    }
    // 过期，清除 attribute
    attrEl.removeAttribute(CTX_TARGET_ATTR);
    console.log(`[Lumio-weibo] ctxTarget (attr): 已过期（${Math.floor(age / 1000)}s > 30s）`);
  }

  // ── 辅机制：chrome.storage.session + selector path ────────
  // 场景：右键元素被虚拟滚动卸载（attribute 跟随元素消失），
  //       但 path 可能定位到新 DOM 中类似位置的元素
  let stored: StoredContextTarget | null = null;
  try {
    const result = await chrome.storage.session.get(STORAGE_KEY);
    stored = result[STORAGE_KEY] as StoredContextTarget | undefined || null;
  } catch (e) {
    console.log(`[Lumio-weibo] ctxTarget (storage): 读取失败`, e);
    return null;
  }
  if (!stored) {
    console.log("[Lumio-weibo] ctxTarget: 无（未记录）");
    return null;
  }
  if (Date.now() - stored.ts > CONTEXT_TARGET_TTL_MS) {
    console.log(`[Lumio-weibo] ctxTarget (storage): 已过期（${Math.floor((Date.now() - stored.ts) / 1000)}s > 30s）`);
    try {
      await chrome.storage.session.remove(STORAGE_KEY);
    } catch {
      // ignore
    }
    return null;
  }
  const el = querySelectorByPath(stored.path);
  if (!el) {
    console.log(`[Lumio-weibo] ctxTarget (storage): path 失效（DOM 已变化）path=${stored.path.slice(0, 80)}...`);
    return null;
  }
  console.log(`[Lumio-weibo] ctxTarget (storage): 有 (tag=${stored.tag}, ${Math.floor((Date.now() - stored.ts) / 1000)}s 前)`);
  return el;
}

// ── URL 类型识别 ──────────────────────────────────────────────

/**
 * 清洗微博 URL 末尾的杂质字符
 *
 * ★ 实测问题：微博 SPA 路由更新 URL 时，会保留原页面的末尾杂质
 *   - mygroups 页 URL 末尾带逗号: weibo.com/mygroups?gid=xxx,
 *   - 跳转到帖子后 URL 仍带逗号: weibo.com/{uid}/{post_id}?pagetype=groupfeed,
 *   - 用户从地址栏复制粘贴时也可能带入逗号/空白
 *
 * ★ 清洗策略：
 *   1. 去掉末尾的逗号、分号、空白、换行
 *   2. 去掉末尾的 ?（空 query 分隔符）
 *   3. 不破坏 URL 内部的合法逗号（query 参数值中的逗号）
 */
function cleanWeiboUrl(url: string): string {
  if (!url) return url;
  // 循环清洗：去掉末尾杂质后可能暴露新的杂质（如逗号后跟空白）
  let cleaned = url;
  for (let i = 0; i < 3; i++) {
    const before = cleaned;
    cleaned = cleaned.replace(/[,\s;]+$/, "");
    cleaned = cleaned.replace(/[?]+$/, "");
    if (cleaned === before) break;
  }
  return cleaned;
}

type WeiboUrlType =
  | { kind: "post"; postId: string }
  | { kind: "profile"; uid: string | null }
  | { kind: "unknown" };

function classifyWeiboUrl(url: string): WeiboUrlType {
  // 1. 单帖子 URL
  let m = url.match(/m\.weibo\.cn\/(?:status|detail)\/([a-zA-Z0-9]+)/);
  if (m) return { kind: "post", postId: m[1] };

  m = url.match(/weibo\.com\/detail\/([a-zA-Z0-9]+)/);
  if (m) return { kind: "post", postId: m[1] };

  // weibo.com/{uid}/{post_id}（uid 纯数字，post_id 5-20 位字母数字）
  // 排除 /u/{uid} 和 /n/{name}（博主主页）
  m = url.match(/weibo\.com\/(\d+)\/([a-zA-Z0-9]{5,20})(?:[/?#]|$)/);
  if (m) return { kind: "post", postId: m[2] };

  // 2. 博主主页 URL
  m = url.match(/weibo\.com\/u\/(\d+)/);
  if (m) return { kind: "profile", uid: m[1] };

  m = url.match(/weibo\.com\/n\/([^/?#]+)/);
  if (m) return { kind: "profile", uid: null };

  m = url.match(/weibo\.com\/([^/?#]+)/);
  if (m) {
    const path = m[1];
    const nonProfilePaths = [
      "detail", "u", "n", "search", "hot", "tv", "p", "album", "myprofile",
      "settings", "logout", "signup", "login", "qr", "about", "help",
    ];
    if (!nonProfilePaths.includes(path) && !/^\d+$/.test(path)) {
      return { kind: "profile", uid: null };
    }
  }

  return { kind: "unknown" };
}

// ── 帖子容器查找（从右键元素向上找） ──────────────────────────

/**
 * 从元素向上找帖子完整容器
 *
 * ★ 优先级（class 选择器跨博主主页和分组浏览页）：
 *   1. div.wbpro-scroller-item（博主主页流式列表项，最稳定，无 hash）
 *   2. [class*='_wrap_']（帖子卡片，class 含 hash 但 _wrap_ 前缀稳定）
 *      ★ 不限标签：博主主页是 article._wrap_ecgcn_2，分组页是 div._wrap_x308k_33
 *   3. div[class*='_body_']（帖子主体，作为兜底）
 *
 * ★ 实测容器样本：
 *   - 博主主页 weibo.com/u/{uid}:    article._wrap_ecgcn_2
 *   - 分组浏览 weibo.com/mygroups:    div._wrap_x308k_33
 *   - 两者都有 _wrap_ 前缀，但标签不同
 */
function findPostContainer(el: Element | null): Element | null {
  if (!el) {
    console.log("[Lumio-weibo] findPostContainer: 元素为 null");
    return null;
  }

  // 向上找 10 层（保险起见，诊断数据显示帖子容器在第 5 层）
  let current: Element | null = el;
  for (let i = 0; i < 10 && current; i++) {
    const cls = current.className || "";
    if (typeof cls === "string") {
      // 1. div.wbpro-scroller-item（博主主页，最稳定，无 hash）
      if (current.tagName === "DIV" && cls.includes("wbpro-scroller-item")) {
        console.log(`[Lumio-weibo] findPostContainer: 命中 wbpro-scroller-item (depth=${i})`);
        return current;
      }
      // 2. [class*='_wrap_']（帖子卡片，跨博主主页和分组浏览页）
      //    ★ 不限标签：article（博主主页）/ div（分组页）都可能
      if (cls.includes("_wrap_")) {
        console.log(`[Lumio-weibo] findPostContainer: 命中 ${current.tagName.toLowerCase()}._wrap_ (depth=${i})`);
        return current;
      }
    }
    current = current.parentElement;
  }
  console.log("[Lumio-weibo] findPostContainer: 10 层内未找到帖子容器");
  return null;
}

/**
 * 用 querySelector 直接查找页面内的帖子容器
 *
 * ★ 用途：详情页 / 无右键上下文时，不能用 findPostContainer(el)（从元素向上找）
 *   详情页没有右键元素，document.body 的 parentElement 是 null，
 *   findPostContainer(document.body) 会立即返回 null
 *
 * ★ 选择器优先级（基于诊断数据）：
 *   1. div.wbpro-scroller-item（博主主页流式列表项，最稳定）
 *   2. article[class*='_wrap_']（详情页 / 博主主页帖子卡片）
 *   3. div[class*='_wrap_']（分组页帖子卡片，标签是 div）
 *
 * ★ 诊断数据样本：
 *   - 详情页 weibo.com/{uid}/{post_id}:  article._wrap_ecgcn_2
 *   - 博主主页 weibo.com/u/{uid}:         article._wrap_ecgcn_2
 *   - 分组浏览 weibo.com/mygroups:         div._wrap_x308k_33
 */
function queryPostContainer(): Element | null {
  const selectors = [
    "div.wbpro-scroller-item",
    "article[class*='_wrap_']",
    "div[class*='_wrap_']",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) {
      console.log(`[Lumio-weibo] queryPostContainer: 命中 ${sel}`);
      return el;
    }
  }
  console.log("[Lumio-weibo] queryPostContainer: 未找到帖子容器");
  return null;
}

/**
 * 从帖子容器提取帖子 URL
 *
 * ★ 提取规则：header 内找 a[href]，href 匹配 weibo.com/{uid}/{post_id}
 *   排除 /u/{uid}（头像/作者名链接）和 s.weibo.com（搜索链接）
 *
 * ★ 诊断数据示例：
 *   <a class="_time_1tpft_33" href="https://weibo.com/5644764907/R6Nus6Xqq">7-2 12:00</a>
 *   <a href="//weibo.com/5644764907/HvyZekN7R">14小时前</a>  ← 相对协议
 */
function extractPostUrlFromContainer(container: Element): string {
  // 在 header 内找帖子 URL（时间链接）
  const header = container.querySelector("header");
  const searchRoot = header || container;

  const candidateLinks = searchRoot.querySelectorAll("a[href]");
  for (const link of Array.from(candidateLinks)) {
    const href = link.getAttribute("href") || "";
    // 匹配 weibo.com/{uid}/{post_id}（uid 纯数字，post_id 5-20 位字母数字）
    // 排除 /u/{uid}（博主主页链接）和 s.weibo.com（搜索链接）
    const m = href.match(/weibo\.com\/(\d+)\/([a-zA-Z0-9]{5,20})(?=[/?#,\s]|$)/);
    if (m) {
      // ★ 用正则匹配的纯 URL（m[0]），不用整个 href
      //   href 可能含尾部杂质（逗号、空白、HTML 转义等），导致 url 污染
      //   实测：微博分组页时间链接 href 末尾会带逗号
      //   例：href="https://weibo.com/5644764907/R8VIQhJK2," → m[0]="weibo.com/5644764907/R8VIQhJK2"
      let url = m[0];
      // 补全协议前缀
      if (url.startsWith("//")) {
        url = "https:" + url;
      } else if (url.startsWith("weibo.com")) {
        url = "https://" + url;
      } else if (url.startsWith("/")) {
        url = "https://weibo.com" + url;
      }
      // ★ 末尾清洗：去掉可能残留的逗号/空白/分号等非 URL 字符
      //   即使正则 lookahead 匹配了逗号，m[0] 不含逗号，
      //   但 href 中间可能有 %2C 等转义，保险起见再清一次
      url = cleanWeiboUrl(url);
      console.log(`[Lumio-weibo] extractPostUrlFromContainer: 提取到帖子 URL = ${url} (raw href=${href.slice(0, 60)})`);
      return url;
    }
  }
  console.log("[Lumio-weibo] extractPostUrlFromContainer: header 内未找到帖子 URL");
  return "";
}

/**
 * 从帖子容器提取作者名
 *
 * ★ 提取规则：
 *   1. a[href*='/u/'][aria-label]（头像链接的 aria-label 属性含作者名）
 *      ★ 限定 href 含 '/u/'：避免匹配帖子内其他 aria-label 元素（如 vip 标签 span[aria-label='vip9']）
 *   2. a[href*='/u/'] span[title]（作者名 span 的 title 属性）
 *   3. a[href*='/u/'] 的 textContent（兜底）
 *
 * ★ 通用词过滤：过滤 "微博正文"/"微博" 等静态默认值
 *   详情页 og 标签和某些 span[title] 会返回这些通用词
 */
function extractAuthorFromContainer(container: Element): string {
  // 1. a[href*='/u/'][aria-label]（最可靠，限定作者链接）
  const ariaLink = container.querySelector("a[href*='/u/'][aria-label]");
  if (ariaLink) {
    const name = ariaLink.getAttribute("aria-label") || "";
    if (name && name.length < 50 && !isWeiboGenericName(name)) return name;
  }

  // 2. a[href*='/u/'] span[title]
  const spanWithTitle = container.querySelector("a[href*='/u/'] span[title]");
  if (spanWithTitle) {
    const title = spanWithTitle.getAttribute("title") || "";
    if (title && title.length < 50 && !isWeiboGenericName(title)) return title;
  }

  // 3. a[href*='/u/'] 的 textContent（兜底）
  const userLink = container.querySelector("a[href*='/u/']");
  if (userLink) {
    const text = (userLink.textContent || "").trim();
    if (text && text.length < 50 && !isWeiboGenericName(text)) return text;
  }

  return "";
}

/**
 * 从帖子容器提取正文（作为 title）
 */
function extractTextFromContainer(container: Element): string {
  const wbtext = container.querySelector("[class*='wbtext']");
  if (wbtext) {
    const text = (wbtext.textContent || "").trim();
    if (text) return text.slice(0, 200);
  }
  return "";
}

/**
 * 规范化图片 URL：补全相对协议
 *
 * ★ 微博 PC 版常用相对协议：
 *   - //wx1.sinaimg.cn/large/xxx.jpg → https://wx1.sinaimg.cn/large/xxx.jpg
 *   - //tvax1.sinaimg.cn/crop.xxx     → https://tvax1.sinaimg.cn/crop.xxx
 *
 * ★ 不修改已经是 http(s):// 的 URL
 */
function normalizeImageUrl(src: string): string {
  if (!src) return "";
  if (src.startsWith("//")) return "https:" + src;
  return src;
}

/**
 * 判断图片 URL 是否为帖子正文图片（而非头像/表情包/小图标）
 *
 * ★ 微博 sinaimg.cn 域名分类：
 *   - wx1-4.sinaimg.cn / tvax1-4.sinaimg.cn: 正文大图（路径含 /large/ /mw2000/ /orj480/）
 *   - tvax1.sinaimg.cn/crop.: 头像（裁剪图，路径含 /crop.）
 *   - h5.sinaimg.cn/upload/: 表情包/超话小图标
 *
 * ★ 支持相对协议：//wx1.sinaimg.cn/large/xxx.jpg 也算正文图
 *   微博 PC 版常用相对协议，旧逻辑要求 src.startsWith("http") 会误过滤第一张正文图
 *
 * ★ 排除规则：
 *   - 路径含 /crop.（头像裁剪图）
 *   - 路径含 /upload/（表情包/图标，非正文图）
 *   - 路径含 /avatar/ /thumb/ /small/（小尺寸图）
 *   - URL 含 50x50 / 100x100 / 360x360（尺寸标识）
 *   - 域名是 h5.sinaimg.cn（表情包/图标域名）
 */
function isPostImage(src: string): boolean {
  if (!src) return false;
  // ★ 支持 http(s):// 和 // 相对协议
  if (!src.startsWith("http") && !src.startsWith("//")) return false;
  if (!src.includes("sinaimg.cn")) return false;

  // 排除表情包/图标域名
  if (src.includes("h5.sinaimg.cn")) return false;

  // 排除头像裁剪图（路径含 /crop.）
  if (src.includes("/crop.")) return false;

  // 排除小尺寸图
  if (
    src.includes("/avatar/") ||
    src.includes("/thumb") ||
    src.includes("/small") ||
    src.includes("50x50") ||
    src.includes("100x100") ||
    src.includes("360x360")
  ) {
    return false;
  }

  // 排除表情包/图标（路径含 /upload/）
  if (src.includes("/upload/")) return false;

  return true;
}

/**
 * 从帖子容器提取缩略图
 *
 * ★ 优先级（基于诊断数据调整）：
 *   1. 帖子正文大图（sinaimg.cn 非头像/非表情包）
 *      ★ 优先大图：livephoto 帖子有 video.poster，但 poster 常是低质量预览
 *         正文大图（如 wx1.sinaimg.cn/large/xxx.jpg）才是用户期待看到的封面
 *   2. video.poster（视频帖子的封面，作为 fallback）
 *
 * ★ 支持懒加载：
 *   微博 PC 版图片可能用懒加载，真实 URL 在 data-src 属性而非 src
 *   提取时同时检查 src 和 data-src，优先用 src，src 无效时用 data-src
 *
 * ★ 支持相对协议：
 *   微博 PC 版常用 //wx1.sinaimg.cn/... 相对协议
 *   返回前用 normalizeImageUrl 补全 https: 前缀
 *
 * ★ 排除项（基于诊断数据）：
 *   - woo-avatar-img class（博主头像）
 *   - /crop. 路径（头像裁剪图）
 *   - h5.sinaimg.cn 域名（表情包/超话小图标）
 *   - /upload/ 路径（表情包/图标）
 *   - 小尺寸图（avatar/thumb/small/50x50/100x100/360x360）
 */
function extractThumbnailFromContainer(container: Element): string {
  // 1. 帖子正文大图（优先）
  // ★ 用 img[src] 或 img[data-src] 选中所有有图片属性的 img
  const imgs = container.querySelectorAll("img[src], img[data-src]");
  console.log(`[Lumio-weibo] extractThumbnailFromContainer: container 内找到 ${imgs.length} 个 img 元素`);
  let idx = 0;
  for (const img of Array.from(imgs)) {
    idx++;
    const cls = img.className || "";
    const rawSrc = img.getAttribute("src") || "";
    const rawDataSrc = img.getAttribute("data-src") || "";

    // 调试日志：输出每个 img 的属性，定位为什么没命中
    console.log(`[Lumio-weibo] img[${idx}]: class=${String(cls).slice(0, 40)}, src=${rawSrc.slice(0, 60)}, data-src=${rawDataSrc.slice(0, 60)}`);

    // 排除头像（woo-avatar-img class）
    if (typeof cls === "string" && cls.includes("woo-avatar-img")) continue;

    // 尝试 src
    if (isPostImage(rawSrc)) {
      const normalized = normalizeImageUrl(rawSrc);
      console.log(`[Lumio-weibo] extractThumbnailFromContainer: 命中正文大图 (src) ${normalized.slice(0, 80)}...`);
      return normalized;
    }
    // src 无效，尝试 data-src
    if (isPostImage(rawDataSrc)) {
      const normalized = normalizeImageUrl(rawDataSrc);
      console.log(`[Lumio-weibo] extractThumbnailFromContainer: 命中正文大图 (data-src) ${normalized.slice(0, 80)}...`);
      return normalized;
    }
  }

  // 2. video.poster（fallback：纯视频帖子无 sinaimg 大图时用 poster）
  const videos = container.querySelectorAll("video");
  for (const v of Array.from(videos)) {
    if (v.poster && v.poster.startsWith("http")) {
      console.log(`[Lumio-weibo] extractThumbnailFromContainer: 命中 video.poster ${v.poster.slice(0, 80)}...`);
      return v.poster;
    }
  }

  console.log("[Lumio-weibo] extractThumbnailFromContainer: 所有 fallback 都失败，返回空");
  return "";
}

/**
 * 判断帖子类型（video / image / unknown）
 */
function detectPostType(container: Element): "video" | "image" | "unknown" {
  const hasVideo = container.querySelectorAll("video").length > 0;
  if (hasVideo) return "video";

  // 排除头像，找帖子内的图片
  const imgs = container.querySelectorAll("img[src*='sinaimg']");
  for (const img of Array.from(imgs)) {
    const cls = img.className || "";
    if (typeof cls === "string" && cls.includes("woo-avatar-img")) continue;
    return "image";
  }
  return "unknown";
}

// ── 博主主页提取（无右键上下文时） ────────────────────────────

/**
 * 从 document.title 提取博主名
 *   - "@杨超越 的个人主页"（PC 版博主主页）
 *   - "杨超越的微博_微博"（移动版博主主页）
 *   - "杨超越 - 微博"（单帖子页）
 *   - "🖤已拍不欠 ​​​ - @杨超越的微博 - 微博"（★ 详情页，title 含正文+作者）
 *   - "明星 - 首页 - 微博"（★ 分组浏览页，title 无博主名，返回分组名作 fallback）
 *
 * ★ 详情页 title 格式："{帖子正文} - @{博主名}的微博 - 微博"
 *   用 / - @([^]+)的微博 - 微博$/ 匹配，提取 @后面的博主名
 *
 * ★ 分组浏览页 title 不是博主名而是分组名（如"明星"/"好友"/"特别关注"），
 *   返回分组名作为 fallback，让 fallback 路径至少有可读 title
 *   （真实博主名仍依赖 extractAuthorFromDom 从 DOM 提取）
 *
 * ★ 详情页 title 常为 "微博正文 - 微博" 或 "微博正文"
 *   这是微博 PC 详情页的默认静态 title（不动态填充真实标题）
 *   必须过滤掉 "微博正文"/"微博" 等通用词，避免污染 author
 */
const WEIBO_GENERIC_NAMES = new Set(["微博正文", "微博", "微博正文-微博", "正文"]);

function extractAuthorFromTitle(title: string): string {
  // ★ 详情页："{帖子正文} - @杨超越的微博 - 微博"
  //   匹配 @后面的博主名（直到"的微博"或空白）
  let m = title.match(/ - @([^\s]+)的微博 - 微博$/);
  if (m) return m[1];

  m = title.match(/^@([^\s]+)\s+的个人主页/);
  if (m) return m[1];

  m = title.match(/^([^_]+?)的微博/);
  if (m) return m[1];

  // 单帖子页：xxx - 微博（标题以 "- 微博" 结尾，前面是作者名）
  m = title.match(/^([^-]+?)\s*-\s*微博$/);
  if (m) {
    const name = m[1].trim();
    if (name && !isWeiboGenericName(name)) return name;
  }

  // ★ 分组浏览页：明星 - 首页 - 微博
  //   匹配 "xxx - 首页" 模式，提取分组名（不是博主名，但比空好）
  //   保留作为 extractAuthorFromDom 失败时的 fallback
  m = title.match(/^([^-]+?)\s*-\s*首页/);
  if (m) {
    const groupName = m[1].trim();
    if (groupName && groupName.length < 20 && !isWeiboGenericName(groupName)) return groupName;
  }

  return "";
}

/**
 * 判断字符串是否为微博通用词（应被过滤）
 *
 * ★ 通用词特征：
 *   - 精确匹配 "微博正文"/"微博"/"正文" 等
 *   - 包含 "微博正文" 子串（如 "微博正文 - 微博" / "微博正文-微博"）
 *   - 单独的 "微博" 或以 "微博" 结尾且长度 ≤ 10
 *
 * ★ 用 includes 而非精确匹配：
 *   实测 document.title = "微博正文 - 微博"，旧逻辑只检查精确匹配，
 *   该值不在集合中导致 fallback 到 document.title 污染 title 字段
 */
function isWeiboGenericName(s: string): boolean {
  if (!s) return true;
  // 精确匹配
  if (WEIBO_GENERIC_NAMES.has(s)) return true;
  // 包含 "微博正文" 子串
  if (s.includes("微博正文")) return true;
  // 单独的 "微博" 或 "微博 - 微博" 等变体
  if (s === "微博" || s === "微博 - 微博") return true;
  return false;
}

/**
 * 从 document.title 提取帖子正文标题
 *
 * ★ 详情页 title 格式："{帖子正文} - @{博主名}的微博 - 微博"
 *   取第一个 " - " 之前的部分作为 title
 *   ★ 若第一个 " - " 前是通用词（如"微博正文"），则返回空
 *
 * ★ 博主主页 title = "@杨超越 的个人主页" / "杨超越的微博_微博"
 *   无 " - " 分隔符，返回空（让 fallback 用 DOM container 提取）
 *
 * ★ 分组浏览页 title = "明星 - 首页 - 微博"
 *   第一个 " - " 前是分组名（不是帖子标题），返回空
 *
 * ★ 静态默认 title = "微博正文 - 微博"（og:title meta 不存在时 fallback 到此值）
 *   用 isWeiboGenericName 过滤，返回空让 fallback 到 DOM container 提取
 */
function extractTitleFromDocumentTitle(title: string): string {
  // 必须含 " - @xxx的微博 - 微博" 模式才是详情页 title
  const m = title.match(/^(.+?) - @[^\s]+的微博 - 微博$/);
  if (m) {
    const t = m[1].trim();
    if (t && !isWeiboGenericName(t)) return t;
  }
  return "";
}

/**
 * 从 DOM 提取博主名（博主主页 / 分组浏览页）
 *
 * ★ 分组浏览页 title="明星 - 首页 - 微博"，extractAuthorFromTitle 识别不到
 *   从 DOM 查找博主名：
 *   1. 帖子列表中第一个帖子 header 内的作者名（a[aria-label] 或 a span[title]）
 *   2. nav/profile 区域的博主名
 *
 * ★ 误匹配修复（关键）：
 *   旧实现 `document.querySelector("[class*='_wrap_']")` 会优先匹配到
 *   侧边栏的 `<div class="_content_wrap_ygi5b_114">`（class 含 `_wrap_`），
 *   而不是帖子卡片 `<article class="_wrap_ecgcn_2">`。
 *   这个误配的 div 内没有 a[aria-label]，导致 author 返回空。
 *
 *   修复策略：按"明确帖子容器"优先级查找
 *     1. div.wbpro-scroller-item（最稳定，class 无 hash，仅博主主页/分组页有）
 *     2. article[class*='_wrap_']（限定 article 标签，避开 div._content_wrap_）
 *     3. 遍历所有 wbpro-scroller-item，找第一个含作者链接的帖子
 */
function extractAuthorFromDom(): string {
  // 1. 优先用最稳定的 wbpro-scroller-item（无 hash，跨博主主页/分组页通用）
  //    遍历所有帖子，找第一个含作者链接的帖子
  //    ★ 用 a[href*='/u/'][aria-label] 精确匹配作者链接（href 含 /u/）
  //      避免匹配帖子内其他 aria-label 元素（如 vip 标签 span[aria-label='vip9']）
  const allPosts = document.querySelectorAll("div.wbpro-scroller-item");
  for (const post of Array.from(allPosts)) {
    const ariaLink = post.querySelector("a[href*='/u/'][aria-label]");
    if (ariaLink) {
      const name = ariaLink.getAttribute("aria-label") || "";
      // 排除多词 aria-label（如 "vip9" / "微博社交会员" 等标签），博主名通常是单字串
      if (name && name.length < 50 && !name.includes(" ")) return name;
    }
    const spanWithTitle = post.querySelector("a[href*='/u/'] span[title]");
    if (spanWithTitle) {
      const title = spanWithTitle.getAttribute("title") || "";
      if (title && title.length < 50) return title;
    }
  }

  // 2. 兜底：限定 article 标签的 _wrap_（避开 div._content_wrap_ 误匹配）
  const articleWrap = document.querySelector("article[class*='_wrap_']");
  if (articleWrap) {
    const ariaLink = articleWrap.querySelector("a[href*='/u/'][aria-label]");
    if (ariaLink) {
      const name = ariaLink.getAttribute("aria-label") || "";
      if (name && name.length < 50 && !name.includes(" ")) return name;
    }
    const spanWithTitle = articleWrap.querySelector("a[href*='/u/'] span[title]");
    if (spanWithTitle) {
      const title = spanWithTitle.getAttribute("title") || "";
      if (title && title.length < 50) return title;
    }
  }

  return "";
}

/**
 * 从 DOM 提取博主头像（博主主页顶部）
 */
function extractAuthorAvatar(): string {
  // 博主主页顶部头像（待诊断数据确认选择器）
  const avatarSelectors = [
    "img[class*='avatar']",
    "img[class*='Avatar']",
    "[class*='profile'] img",
    "[class*='header'] img[class*='avatar']",
  ];
  for (const sel of avatarSelectors) {
    try {
      const el = document.querySelector(sel) as HTMLImageElement | null;
      if (el?.src && el.src.startsWith("http")) {
        return el.src;
      }
    } catch {
      // 选择器语法错误
    }
  }
  return "";
}

/**
 * 从 meta 标签提取缩略图（多重 fallback）
 *
 * ★ 微博详情页 og:image 常为空，需多重 fallback：
 *   1. og:image（标准）
 *   2. twitter:image（部分页面有）
 *   3. itemprop="image"（微数据）
 *   4. itemprop="thumbnailUrl"
 */
function extractThumbnailFromMeta(): string {
  const metaSelectors = [
    'meta[property="og:image"]',
    'meta[name="og:image"]',
    'meta[name="twitter:image"]',
    'meta[property="twitter:image"]',
    'meta[itemprop="image"]',
    'meta[itemprop="thumbnailUrl"]',
  ];
  for (const sel of metaSelectors) {
    const el = document.querySelector(sel) as HTMLMetaElement | null;
    const content = el?.getAttribute("content") || "";
    if (content && content.startsWith("http")) return content;
  }
  return "";
}

/**
 * 从页面任意 video 元素提取 poster（详情页视频封面兜底）
 */
function extractVideoPosterFromPage(): string {
  const videos = document.querySelectorAll("video");
  for (const v of Array.from(videos)) {
    if (v.poster && v.poster.startsWith("http")) return v.poster;
  }
  return "";
}

/**
 * 从页面文章正文区域提取首张图片（详情页图片帖兜底）
 *
 * ★ 用 isPostImage 精确过滤：
 *   排除头像/表情包/小图标/小尺寸图
 *   只保留正文大图（sinaimg.cn 非头像/非表情包）
 *
 * ★ 支持懒加载和相对协议：
 *   - 检查 data-src 属性
 *   - 用 normalizeImageUrl 补全 https: 前缀
 */
function extractFirstImageFromArticle(): string {
  const imgs = document.querySelectorAll("img[src], img[data-src]");
  for (const img of Array.from(imgs)) {
    const cls = img.className || "";
    if (typeof cls === "string" && cls.includes("woo-avatar-img")) continue;
    const rawSrc = img.getAttribute("src") || "";
    const rawDataSrc = img.getAttribute("data-src") || "";
    if (isPostImage(rawSrc)) return normalizeImageUrl(rawSrc);
    if (isPostImage(rawDataSrc)) return normalizeImageUrl(rawDataSrc);
  }
  return "";
}

// ── 主提取函数 ──────────────────────────────────────────────

export async function extractWeibo(): Promise<ExtractResult | null> {
  // ★ 清洗 URL：去掉 SPA 路由残留的末尾逗号/空白
  const url = cleanWeiboUrl(window.location.href);
  const urlType = classifyWeiboUrl(url);
  console.log(`[Lumio-weibo] extractWeibo: url=${url}, type=${urlType.kind}`);

  if (urlType.kind === "unknown") {
    console.log("[Lumio-weibo] URL 类型 unknown，返回 null");
    return null;
  }

  // ── 博主主页模式 ──────────────────────────────────────────
  if (urlType.kind === "profile") {
    // ★ 优先：从右键上下文提取单个帖子（30 秒内有效）
    // 用户右键某帖子的图片/video 时，setContextMenuTarget 把元素 path 存到 storage.session
    // getFreshContextMenuTarget 用 querySelector 重新定位元素
    // ★ 跨 content script 实例可用（path 是 DOM 稳定位置，不依赖模块级变量）
    const ctxTarget = await getFreshContextMenuTarget();
    if (ctxTarget) {
      console.log(`[Lumio-weibo] ctxTarget tag=${ctxTarget.tagName}, class=${(ctxTarget.className || "").slice(0, 50)}`);
      const container = findPostContainer(ctxTarget);
      console.log(`[Lumio-weibo] container: ${container ? container.tagName + "." + (container.className || "").slice(0, 50) : "null"}`);
      if (container) {
        const postUrl = extractPostUrlFromContainer(container);
        console.log(`[Lumio-weibo] postUrl: ${postUrl || "(空)"}`);
        if (postUrl) {
          const author = extractAuthorFromContainer(container);
          const title = extractTextFromContainer(container);
          const thumbnail = extractThumbnailFromContainer(container);
          const mediaType = detectPostType(container);
          console.log(`[Lumio-weibo] 成功提取帖子: url=${postUrl}, title=${title.slice(0, 30)}, author=${author}, type=${mediaType}`);

          return {
            url: postUrl, // ★ 帖子 URL（非博主主页 URL），后端解析此 URL
            title,
            author,
            platform: "weibo",
            thumbnail,
            duration: null,
            type: mediaType === "unknown" ? "url" : mediaType,
          };
        }
      }
    }

    // 无右键上下文 / 找不到帖子容器 → 返回博主信息触发批量
    console.log("[Lumio-weibo] 无右键上下文或未提取到帖子，返回博主信息触发批量");
    // ★ 优先 DOM 提取真实博主名（a[href*='/u/'][aria-label]），title 仅作 fallback
    //   分组页 title="明星 - 首页 - 微博" 是分组名不是博主名，
    //   DOM 提取能拿到真实博主名（如"杨超越"）
    const author =
      extractAuthorFromDom() ||
      extractAuthorFromTitle(document.title);
    // ★ 缩略图：优先博主头像，兜底 meta + 文章首图
    //   分组页博主头像选择器可能不匹配，加多重 fallback 提高成功率
    const thumbnail =
      extractAuthorAvatar() ||
      extractThumbnailFromMeta() ||
      extractFirstImageFromArticle();
    // ★ title 不能用 document.title（分组浏览页是"明星 - 首页 - 微博"等无意义标题）
    //   用 author + "的微博主页" 作为可读标题；author 为空时 fallback 到 URL
    const profileTitle = author ? `${author}的微博主页` : "微博博主主页";

    return {
      url, // 博主主页 URL
      title: profileTitle,
      author,
      platform: "weibo",
      thumbnail,
      duration: null,
      type: "profile", // 触发批量分支
    };
  }

  // ── 单帖子模式（详情页，从博主主页点击帖子后进入） ────────────────
  //
  // ★ 微博 PC 详情页 URL：https://weibo.com/{uid}/{post_id}
  //   - og:title 是静态默认值 "微博正文"（不动态填充），不能用
  //   - 真实标题在 DOM 的帖子容器内（wbtext 元素）
  //   - 真实作者在 DOM 的 header 内（a[href*='/u/'][aria-label]）
  //   - 后端 WeiboProvider.extract_info 也能正确解析此 URL（调 m.weibo.cn API）
  //
  // ★ 提取优先级：
  //   1. queryPostContainer 用 querySelector 直接查找帖子容器
  //      （★ 不能用 findPostContainer(document.body)，body 顶层元素 parentElement 为 null，
  //        循环立即结束返回 null，导致 container 为空，所有 container 相关提取都失败）
  //   2. extractAuthorFromDom 从 DOM 找博主名（跨博主主页/详情页通用）
  //   3. og.thumbnail 兜底缩略图
  //   4. title 用 DOM 正文，og.title 过滤掉 "微博正文" 等通用词
  const og = commonOg();
  const container = queryPostContainer();

  // ★ author：优先 DOM 提取（container 内的 a[href*='/u/']），再 fallback 到 title
  //   详情页 document.title 常为 "微博正文 - 微博"，extractAuthorFromTitle 已过滤通用词
  const containerAuthor = container ? extractAuthorFromContainer(container) : "";
  const domAuthor = extractAuthorFromDom();
  const titleAuthor = extractAuthorFromTitle(document.title);
  const author = containerAuthor || domAuthor || titleAuthor;

  // ★ title 优先级：
  //   1. container 内 wbtext 正文（最准确，诊断数据已确认）
  //   2. 从 document.title 提取（详情页格式 "{正文} - @xxx的微博 - 微博"）
  //   3. og.title（过滤通用词，包括 "微博正文 - 微博" 等变体）
  //   4. 兜底 postId
  const containerTitle = container ? extractTextFromContainer(container) : "";
  const docTitleExtracted = extractTitleFromDocumentTitle(document.title);
  const ogTitleFiltered = isWeiboGenericName(og.title) ? "" : og.title;
  const title =
    containerTitle ||
    docTitleExtracted ||
    ogTitleFiltered ||
    `微博 ${urlType.postId.slice(0, 8)}`;

  // ★ thumbnail：多重 fallback，确保详情页也能拿到缩略图
  //   1. container 内提取（视频 poster / sinaimg 图片）
  //   2. meta 标签（og:image / twitter:image / itemprop）
  //   3. 页面任意 video poster
  //   4. 文章正文首图
  //   5. og.thumbnail（commonOg 兜底）
  console.log(`[Lumio-weibo] thumbnail 提取: container=${container ? "有" : "无"}, og.thumbnail=${og.thumbnail ? "有" : "无"}`);
  const containerThumb = container ? extractThumbnailFromContainer(container) : "";
  const metaThumb = extractThumbnailFromMeta();
  const videoPosterThumb = extractVideoPosterFromPage();
  const articleImgThumb = extractFirstImageFromArticle();
  console.log(`[Lumio-weibo] thumbnail fallback: containerThumb=${containerThumb ? "有" : "空"}, metaThumb=${metaThumb ? "有" : "空"}, videoPoster=${videoPosterThumb ? "有" : "空"}, articleImg=${articleImgThumb ? "有" : "空"}`);
  const thumbnail =
    containerThumb || metaThumb || videoPosterThumb || articleImgThumb || og.thumbnail || "";
  const mediaType = container ? detectPostType(container) : "unknown";
  // ★ 详情页 detectPostType 失败时，用 thumbnail 是否存在推断类型
  const inferredType =
    mediaType === "unknown"
      ? thumbnail
        ? "image" // 有缩略图但 container 类型未知，推断为 image（保守）
        : "url"
      : mediaType;

  return {
    url,
    title,
    author,
    platform: "weibo",
    thumbnail,
    duration: null,
    type: inferredType,
  };
}
