/**
 * i18n.ts — Lumio 官网中英双语切换
 *
 * 设计：
 *   1. 字典扁平 key（点号路径）：'hero.title' / 'features.01.desc' / ...
 *   2. data-i18n="key" → 元素 textContent（纯文本）
 *   3. data-i18n-html="key" → 元素 innerHTML（含 <br> / <span> 等富文本）
 *   4. data-i18n-attr="attr:key,attr2:key2" → 元素属性翻译（如 aria-label / title / placeholder）
 *   5. localStorage('lumio-lang') 持久化，默认根据 <html lang> + 浏览器语言推断
 *   5. 切换时同时更新 <html lang> 属性，利于 SEO + 无障碍
 *
 * 字典范围：
 *   - 导航 / Hero / 平台 / 功能 4 卖点 / 演示 / 下载区 — 完整双语
 *   - FAQ — summary 双语，body 保留中文（技术细节，英文用户可参考 GitHub 文档）
 *   - Footer — 由 SiteFooter 组件内部处理（如有 data-i18n 则切换）
 */

type Lang = 'zh' | 'en';

const dict: Record<Lang, Record<string, string>> = {
  zh: {
    // ─── 导航 ───
    'nav.features': '功能',
    'nav.demo': '演示',
    'nav.faq': 'FAQ',
    'nav.download': '下载',
    'nav.menu.open': '打开菜单',
    'nav.menu.close': '关闭菜单',

    // ─── Hero ───
    'hero.title': '把喜欢的一切<br /><span class="text-gradient">留下来</span>',
    'hero.subtitle': '粘贴链接，Lumio 替你整理。<br class="hidden md:inline" />爱豆照片、舞台直拍、Live Photo、视频原档，原画质自动入库。',
    'hero.cta.download': '下载 Lumio',
    'hero.cta.source': '查看源码',
    'hero.badge.windows': 'Windows 10+',
    'hero.badge.ffmpeg': '内置 ffmpeg',

    // ─── 痛点 ───
    'pain.l1': '看到的，',
    'pain.l2': '留不住。',
    'pain.l3': '水印挡脸，视频被压缩，文件夹越堆越乱，想找的图永远在收藏夹里吃灰。',

    // ─── 平台区 ───
    'platforms.eyebrow': '8 大平台，粘贴就识别',
    'platforms.hint': '点击图标跳转官网',

    // ─── 功能卖点 ───
    'features.eyebrow': '§ Features',
    'features.title': '不只是下载器，<br />是<span class="text-gradient">你的素材库</span>',
    'features.desc': '从保存到管理，Lumio 覆盖媒体收藏的完整链路。图片、视频、Live Photo，原档入库。',

    'features.01.eyebrow': '§ 01 — Parse',
    'features.01.title': '解析<br />原档位，无折损',
    'features.01.desc': '粘贴微博、小红书、抖音、B站、Instagram、YouTube、X 的分享链接，自动识别平台，秒级解析出高清图片和视频。不用选平台，不用调参数。',
    'features.01.pill1': '图片+视频',
    'features.01.pill2': '原画质',
    'features.01.pill3': '自动识别',
    'features.01.pill4': '缩略图预览',

    'features.02.eyebrow': '§ 02 — No Watermark',
    'features.02.title': '画质<br />CDN 直链，无水印',
    'features.02.desc': '直接抓取平台 CDN 原始媒体，跳过二次压缩或水印处理。爱豆照片、舞台直拍、Live Photo、视频原档，全部原画质保存。',
    'features.02.pill1': 'CDN 直链',
    'features.02.pill2': '无水印',
    'features.02.pill3': '视频原档',
    'features.02.pill4': 'Live Photo',

    'features.03.eyebrow': '§ 03 — Extension',
    'features.03.title': '插件<br />右键即送，免复制',
    'features.03.desc': 'Chrome / Edge 浏览器扩展，右键即可发送到 Lumio。桌面端自动收到，Inbox 收件箱预览，点击下载。IG 一次性注入提取直链，不调 API，不触发风控。',
    'features.03.pill1': '右键即存',
    'features.03.pill2': 'Chrome / Edge',
    'features.03.pill3': 'IG 安全提取',

    'features.04.eyebrow': '§ 04 — Library',
    'features.04.title': '管理<br />搜索、分类、收藏',
    'features.04.desc': '下载后的内容不会散落在各个文件夹。所有图片视频自动进入素材库，支持按标题、作者、URL、文件路径全文搜索，缩略图网格、收藏、Collections 分类、内置播放器。再也不用满电脑找图片，找视频也不用切文件夹。',
    'features.04.pill1': '图片+视频',
    'features.04.pill2': '全文搜索',
    'features.04.pill3': '缩略图网格',
    'features.04.pill4': 'Collections 分类',
    'features.04.pill5': '收藏',
    'features.04.pill6': '内置播放器',

    // ─── 演示区 ───
    'demo.eyebrow': '§ Demo',
    'demo.title': '<span class="text-gradient">演示</span>',
    'demo.desc': '从粘贴链接到入队下载，从右键扩展到收件箱，完整链路演示。',
    'demo.01.eyebrow': '§ Demo 01',
    'demo.01.title': '粘贴链接 → 解析 → 入队',
    'demo.01.desc': '自动识别 8 大平台，秒级解析出高清图片和视频，缩略图预览后一键入队。',
    'demo.02.eyebrow': '§ Demo 02',
    'demo.02.title': '打开详情帖 → 插件 → 发送',
    'demo.02.desc': '在社交媒体详情页打开 Lumio 插件，自动解析提取当前页媒体元数据，一键发送到 Inbox 收件箱。',
    'demo.feature.01': '零配置，开箱即用',
    'demo.feature.02': '原画质，无水印',
    'demo.feature.03': '自动入库，统一管理',

    // ─── FAQ ───
    'faq.eyebrow': '§ FAQ',
    'faq.title': '常见<span class="text-gradient">问题</span>',
    'faq.desc': '关于下载、画质、平台支持、隐私的几个核心问题。',
    'faq.q1': 'Lumio 需要登录账号吗？',
    'faq.q2': '下载的画质是原画质吗？',
    'faq.q3': '会触发风控或封号吗？',
    'faq.q4': '支持 macOS 和 Linux 吗？',
    'faq.q5': '下载的内容存在哪里？数据安全吗？',
    'faq.q6': '浏览器扩展怎么用？安全吗？',
    'faq.q7': '是开源的吗？收费吗？',
    'faq.q8': '需要代理吗？国外平台怎么下载？',
    'faq.q9': 'Apify Token 是什么？怎么获取？',
    'faq.q10': '下载的视频用什么播放器？',

    // ─── 下载区 ───
    'download.eyebrow': '§ Download',
    'download.title': '打开<span class="text-gradient">Lumio</span>',
    'download.desc': 'Windows / macOS / Linux，开源免费，开箱即用。安装包内置 Python 运行时和 ffmpeg。',
    'download.btn': '立即下载',
    'download.github': '关注 GitHub',
    'download.hosting': '文件托管于 GitHub Releases · 点击下载自动获取最新版本',

    // ─── 下载弹窗 ───
    'dialog.title': '选择你的平台',
    'dialog.sub': 'MIT License · 开源免费',
    'dialog.close': '关闭下载弹窗',
    'dialog.fallback.title': '前往 GitHub 下载',
    'dialog.fallback.hint': '无法自动获取版本信息，请直接前往 Releases 页面选择对应平台安装包。',
    'dialog.fallback.btn': '打开 GitHub Releases',
    'dialog.all': '查看所有版本 →',
    'dialog.download': '下载',
    'dialog.source.mirror': '🇨🇳 国内镜像',
    'dialog.source.direct': '🌐 GitHub 直链',
    'dialog.source.hint': '镜像由 Cloudflare CDN 加速，国内无需代理',

    // ─── 更新日志 ───
    'changelog.eyebrow': '§ Changelog',
    'changelog.title': '更新<span class="text-gradient">日志</span>',
    'changelog.latest': '最新版本',
    'changelog.summary': '更新日志',
    'changelog.hint': '点击展开',
    'changelog.entry.link': '查看完整 Release →',
    'changelog.footer.link': '查看所有版本 →',

    // ─── 控制条 ───
    'ctrl.sound.on': '关闭音效',
    'ctrl.sound.off': '开启音效',
    'ctrl.theme.dark': '切换亮色模式',
    'ctrl.theme.light': '切换暗夜模式',
    'ctrl.lang.zh': 'Switch to English',
    'ctrl.lang.en': '切换中文',

    // ─── Footer ───
    'footer.tagline': '把喜欢的一切，留下来。',
    'footer.col.product': '产品',
    'footer.col.resources': '资源',
    'footer.col.community': '社区',
    'footer.col.legal': '法律',
    'footer.link.features': '功能',
    'footer.link.download': '下载',
    'footer.link.changelog': '更新日志',
    'footer.link.faq': 'FAQ',
    'footer.link.github': 'GitHub 源码',
    'footer.link.extension': '浏览器扩展',
    'footer.link.docs': '技术文档',
    'footer.link.issues': '问题反馈',
    'footer.link.discussions': '功能讨论',
    'footer.link.privacy': '隐私声明',
    'footer.link.terms': '使用条款',
    'footer.tech.built': 'Built with',
    'footer.legal.line': '本软件仅供个人学习使用，请遵守各平台用户协议与当地版权法规 · 不收集任何用户数据',
    'footer.privacy.summary': '隐私声明',
    'footer.terms.summary': '使用条款',
  },

  en: {
    // ─── Nav ───
    'nav.features': 'Features',
    'nav.demo': 'Demo',
    'nav.faq': 'FAQ',
    'nav.download': 'Download',
    'nav.menu.open': 'Open menu',
    'nav.menu.close': 'Close menu',

    // ─── Hero ───
    'hero.title': 'Keep everything you love,<br /><span class="text-gradient">forever</span>',
    'hero.subtitle': 'Paste a link, let Lumio organize it.<br class="hidden md:inline" />Idol photos, stage fancams, Live Photos, raw video — all archived in original quality.',
    'hero.cta.download': 'Download Lumio',
    'hero.cta.source': 'View Source',
    'hero.badge.windows': 'Windows 10+',
    'hero.badge.ffmpeg': 'ffmpeg bundled',

    // ─── Pain point ───
    'pain.l1': 'You see it,',
    'pain.l2': "but can't keep it",
    'pain.l3': 'Watermarks cover faces, videos get re-compressed, folders pile up, and the photo you wanted is forever lost in your bookmarks.',

    // ─── Platforms ───
    'platforms.eyebrow': '8 platforms, auto-detected on paste',
    'platforms.hint': 'Click icon to visit official site',

    // ─── Features ───
    'features.eyebrow': '§ Features',
    'features.title': 'Not just a downloader,<br />it\'s your <span class="text-gradient">media library</span>',
    'features.desc': 'From saving to managing, Lumio covers the full pipeline of media collecting. Photos, videos, Live Photos — archived in original quality.',

    'features.01.eyebrow': '§ 01 — Parse',
    'features.01.title': 'Parse<br />Original quality, no loss',
    'features.01.desc': 'Paste a share link from Weibo, Xiaohongshu, Douyin, Bilibili, Instagram, YouTube, or X. Lumio auto-detects the platform and resolves HD photos and videos in seconds. No manual platform selection, no parameters to tune.',
    'features.01.pill1': 'Photo + Video',
    'features.01.pill2': 'Original quality',
    'features.01.pill3': 'Auto-detect',
    'features.01.pill4': 'Thumbnail preview',

    'features.02.eyebrow': '§ 02 — No Watermark',
    'features.02.title': 'Quality<br />CDN direct, no watermark',
    'features.02.desc': 'Fetch raw media straight from platform CDNs, bypassing re-compression and watermarking. Idol photos, stage fancams, Live Photos, raw video — all saved in original quality.',
    'features.02.pill1': 'CDN direct',
    'features.02.pill2': 'No watermark',
    'features.02.pill3': 'Raw video',
    'features.02.pill4': 'Live Photo',

    'features.03.eyebrow': '§ 03 — Extension',
    'features.03.title': 'Extension<br />Right-click to send, no copy',
    'features.03.desc': 'Chrome / Edge browser extension. Right-click any page to send media to Lumio. Desktop receives it instantly, Inbox previews it, one click to download. IG uses one-shot injection to extract direct URLs — no API calls, no risk of account flags.',
    'features.03.pill1': 'Right-click save',
    'features.03.pill2': 'Chrome / Edge',
    'features.03.pill3': 'IG safe extract',

    'features.04.eyebrow': '§ 04 — Library',
    'features.04.title': 'Manage<br />Search, categorize, favorite',
    'features.04.desc': 'Downloaded content no longer scatters across folders. All photos and videos auto-enter the library, with full-text search across title, author, URL, and file path. Thumbnail grid, favorites, Collections, and a built-in player. No more hunting through folders for that one photo or video.',
    'features.04.pill1': 'Photo + Video',
    'features.04.pill2': 'Full-text search',
    'features.04.pill3': 'Thumbnail grid',
    'features.04.pill4': 'Collections',
    'features.04.pill5': 'Favorites',
    'features.04.pill6': 'Built-in player',

    // ─── Demo ───
    'demo.eyebrow': '§ Demo',
    'demo.title': '<span class="text-gradient">Demo</span>',
    'demo.desc': 'From pasting a link to queuing a download, from right-click extension to Inbox — the full pipeline, demoed end-to-end.',
    'demo.01.eyebrow': '§ Demo 01',
    'demo.01.title': 'Paste link → Parse → Enqueue',
    'demo.01.desc': 'Auto-detects 8 platforms, resolves HD photos and videos in seconds, thumbnail preview before one-click enqueue.',
    'demo.02.eyebrow': '§ Demo 02',
    'demo.02.title': 'Open post → Extension → Send',
    'demo.02.desc': 'Open the Lumio extension on any social media post page. It auto-parses the current page\'s media metadata and sends it to the Inbox in one click.',
    'demo.feature.01': 'Zero config, works out of the box',
    'demo.feature.02': 'Original quality, no watermark',
    'demo.feature.03': 'Auto-archive, unified management',

    // ─── FAQ ───
    'faq.eyebrow': '§ FAQ',
    'faq.title': 'Frequently <span class="text-gradient">Asked</span>',
    'faq.desc': 'Core questions about downloading, quality, platform support, and privacy.',
    'faq.q1': 'Does Lumio require an account?',
    'faq.q2': 'Is the download quality original?',
    'faq.q3': 'Will it trigger rate limits or account flags?',
    'faq.q4': 'Does it support macOS and Linux?',
    'faq.q5': 'Where is downloaded content stored? Is my data safe?',
    'faq.q6': 'How do I use the browser extension? Is it safe?',
    'faq.q7': 'Is it open source? Is there a paid tier?',
    'faq.q8': 'Do I need a VPN? How do I download from foreign platforms?',
    'faq.q9': 'What is an Apify Token? How do I get one?',
    'faq.q10': 'Which video player should I use for downloads?',

    // ─── Download ───
    'download.eyebrow': '§ Download',
    'download.title': 'Get <span class="text-gradient">Lumio</span>',
    'download.desc': 'Windows / macOS / Linux. Open source, free, works out of the box. Bundled with Python runtime and ffmpeg.',
    'download.btn': 'Download Now',
    'download.github': 'Star on GitHub',
    'download.hosting': 'Hosted on GitHub Releases · Always fetches the latest version',

    // ─── Download dialog ───
    'dialog.title': 'Choose your platform',
    'dialog.sub': 'MIT License · Free & Open Source',
    'dialog.close': 'Close download dialog',
    'dialog.fallback.title': 'Get it on GitHub',
    'dialog.fallback.hint': 'Could not auto-fetch version info. Please visit the Releases page to pick the right installer for your platform.',
    'dialog.fallback.btn': 'Open GitHub Releases',
    'dialog.all': 'View all versions →',
    'dialog.download': 'Download',
    'dialog.source.mirror': '🇨🇳 Mirror (CN)',
    'dialog.source.direct': '🌐 GitHub Direct',
    'dialog.source.hint': 'Mirror powered by Cloudflare CDN, no proxy needed',

    // ─── Changelog ───
    'changelog.eyebrow': '§ Changelog',
    'changelog.title': 'Change<span class="text-gradient">log</span>',
    'changelog.latest': 'Latest version',
    'changelog.summary': 'Changelog',
    'changelog.hint': 'Click to expand',
    'changelog.entry.link': 'View full Release →',
    'changelog.footer.link': 'View all versions →',

    // ─── Control strip ───
    'ctrl.sound.on': 'Disable sound',
    'ctrl.sound.off': 'Enable sound',
    'ctrl.theme.dark': 'Switch to light mode',
    'ctrl.theme.light': 'Switch to dark mode',
    'ctrl.lang.zh': 'Switch to English',
    'ctrl.lang.en': '切换中文',

    // ─── Footer ───
    'footer.tagline': 'Keep everything you love, forever.',
    'footer.col.product': 'Product',
    'footer.col.resources': 'Resources',
    'footer.col.community': 'Community',
    'footer.col.legal': 'Legal',
    'footer.link.features': 'Features',
    'footer.link.download': 'Download',
    'footer.link.changelog': 'Changelog',
    'footer.link.faq': 'FAQ',
    'footer.link.github': 'GitHub Source',
    'footer.link.extension': 'Browser Extension',
    'footer.link.docs': 'Tech Docs',
    'footer.link.issues': 'Report Issues',
    'footer.link.discussions': 'Feature Discussions',
    'footer.link.privacy': 'Privacy Notice',
    'footer.link.terms': 'Terms of Use',
    'footer.tech.built': 'Built with',
    'footer.legal.line': 'For personal study only. Comply with each platform\'s ToS and local copyright law · No user data collected',
    'footer.privacy.summary': 'Privacy Notice',
    'footer.terms.summary': 'Terms of Use',
  },
};

const STORAGE_KEY = 'lumio-lang';
const LANG_ATTR = 'data-lang';

function detectInitialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'zh' || saved === 'en') return saved;
  } catch {}

  // 浏览器语言推断
  const nav = navigator.language?.toLowerCase() || '';
  if (nav.startsWith('zh')) return 'zh';
  return 'en';
}

function applyLang(lang: Lang) {
  const table = dict[lang];

  // 纯文本
  document.querySelectorAll<HTMLElement>('[data-i18n]').forEach((el) => {
    const key = el.dataset.i18n || '';
    const val = table[key];
    if (val !== undefined) el.textContent = val;
  });

  // 富文本（含 <br> / <span>）
  document.querySelectorAll<HTMLElement>('[data-i18n-html]').forEach((el) => {
    const key = el.dataset.i18nHtml || '';
    const val = table[key];
    if (val !== undefined) el.innerHTML = val;
  });

  // 属性翻译（aria-label / title / placeholder 等）
  // 格式：data-i18n-attr="aria-label:key1,title:key2"
  document.querySelectorAll<HTMLElement>('[data-i18n-attr]').forEach((el) => {
    const spec = el.dataset.i18nAttr || '';
    spec.split(',').forEach((pair) => {
      const [attr, key] = pair.split(':').map((s) => s.trim());
      if (!attr || !key) return;
      const val = table[key];
      if (val !== undefined) el.setAttribute(attr, val);
    });
  });

  // 更新 <html lang> 和 data-lang 属性（initI18n 读取 data-lang 判断当前语言）
  document.documentElement.setAttribute('lang', lang === 'zh' ? 'zh-CN' : 'en');
  document.documentElement.setAttribute(LANG_ATTR, lang);
  try { localStorage.setItem(STORAGE_KEY, lang); } catch {}

  // 同步切换按钮文案
  const langBtn = document.getElementById('lang-toggle');
  if (langBtn) {
    const label = table['ctrl.lang.' + lang] || '';
    if (label) langBtn.setAttribute('aria-label', label);
    const labelEl = langBtn.querySelector('[data-lang-letter]');
    if (labelEl) labelEl.textContent = lang === 'zh' ? 'EN' : '中';
  }
}

export function initI18n() {
  if (typeof window === 'undefined') return;

  const lang = detectInitialLang();
  applyLang(lang);

  // 切换按钮
  const langBtn = document.getElementById('lang-toggle');
  if (langBtn) {
    langBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const current = (document.documentElement.getAttribute(LANG_ATTR) as Lang) ||
        (localStorage.getItem(STORAGE_KEY) as Lang) || 'zh';
      const next: Lang = current === 'zh' ? 'en' : 'zh';
      applyLang(next);
    });
  }
}

// 暴露给 window 方便调试
if (typeof window !== 'undefined') {
  (window as any).__lumioI18n = { applyLang, dict };
}
