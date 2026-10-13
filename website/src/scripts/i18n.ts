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
 *   - FAQ — 问题 + 回答全部双语（回答为富文本 innerHTML 替换）
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
    'platforms.cnFriendly': '国内用户友好：微博 / 小红书 / 抖音 / B站 / 快手 全部支持，无需任何特殊网络，本地运行开箱即用',

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
    'faq.a1': '<p>不需要。Lumio 是纯本地工具，无需注册、无需登录。下载 Instagram 内容需要导入你的 IG cookie（Netscape 格式），下载 X 图片和批量枚举需要导入 auth_token + ct0 cookie，其他 6 大平台（YouTube / B站 / 抖音 / 快手 / 微博 / 小红书）开箱即用，无需任何凭证。</p>',
    'faq.a2': '<p>是的。所有平台默认下载 API 返回档位内的最高画质：</p><ul><li><strong>YouTube</strong>：4K / 8K + 自动合并音频（用户手动选择格式）</li><li><strong>Instagram</strong>：视频取 width 最大档位，图片取 image_versions2.candidates 最大档位</li><li><strong>X (Twitter)</strong>：图片请求原图（?format=jpg&name=orig），视频取最高 bitrate</li><li><strong>B站</strong>：DASH fnval=16 + qn=127 + fourk=1 请求最高档</li><li><strong>抖音</strong>：aweme detail API 遍历 bit_rate[] 取最高档（已知限制：60 帧 H.265 超高清原画需 app API）</li><li><strong>微博 / 小红书 / 快手</strong>：取 API 返回的最高分辨率</li></ul><p>所有下载均无平台水印。</p>',
    'faq.a3': '<p>Lumio 在设计上避免触发风控：</p><ul><li><strong>Instagram</strong>：右键 IG 页面时浏览器扩展一次性注入提取 DOM 直链，不调 IG API，不触发自动化检测</li><li><strong>X</strong>：用 GraphQL API + 你的 cookie，频率克制，不批量爬取</li><li><strong>抖音</strong>：自动获取 ttwid 访客标识，无需用户 cookie 或 a_bogus 签名</li><li><strong>批量下载</strong>：内建指数退避重试（5s → 15s → 30s），控制节奏</li></ul><p>但仍建议合理使用，避免短时间内下载几百条内容。</p>',
    'faq.a4': '<p>支持。三平台安装包已通过 GitHub Actions 自动构建并发布，点击首页「下载 Lumio」即可选择对应平台：</p><ul><li><strong>Windows</strong>：NSIS 安装包（路径选择 + 卸载清理）</li><li><strong>macOS</strong>：DMG（分 x64 / arm64 架构）</li><li><strong>Linux</strong>：AppImage / .deb / .rpm</li></ul><p>国内用户下载弹窗默认走 Cloudflare CDN 镜像加速，无需代理即可下载。</p>',
    'faq.a5': '<p>所有数据完全本地存储，不上传任何服务器：</p><ul><li><strong>素材库</strong>：~/.lumio/library.db（SQLite，含元数据 + content_hash）</li><li><strong>下载历史</strong>：~/.lumio/history.json</li><li><strong>配置</strong>：~/.lumio/config.json</li><li><strong>下载队列</strong>：~/.lumio/queue.json（原子写入防崩溃截断）</li><li><strong>媒体文件</strong>：用户指定目录，自动入库</li></ul><p>Lumio 不收集任何用户数据，不发送任何遥测。删除 ~/.lumio/ 即可完全清除。</p>',
    'faq.a6': '<p>Chrome / Edge 浏览器扩展（Manifest V3）使用流程：</p><ol><li>在社交媒体详情页打开 Lumio 插件</li><li>插件自动解析提取当前页媒体元数据</li><li>点击发送，一键发送到 Inbox 收件箱</li></ol><p>安全方面：</p><ul><li>扩展仅读取页面 DOM 元数据，不读取你的私信或聊天</li><li>数据通过本地 API（127.0.0.1:38900）发送到桌面端，不经过任何外部服务器</li><li>IG 一次性注入提取直链，不常驻 content script，不调 IG API</li><li>开源代码，可自行审计</li></ul>',
    'faq.a7': '<p>Lumio 是 <strong>MIT 协议开源</strong>，完全免费，无任何付费功能。源码托管在 <a href={GITHUB_URL} target="_blank" rel="noopener" class="faq-link">GitHub</a>，欢迎 Star / Issue / PR。</p>',
    'faq.a8': '<p><strong>分平台说明：</strong></p><ul><li><strong>国内平台</strong>（微博 / 小红书 / 抖音 / B站 / 快手）—— 无需代理，直接使用。</li><li><strong>国外平台</strong>（YouTube / Instagram / X）—— 中国大陆网络环境下需要自备代理工具。</li></ul><p>Lumio 启动时会自动检测外网连通性（尝试连接 youtube.com:443），失败会推送通知提醒。</p><p><strong>代理配置：</strong>Lumio 会自动读取系统代理（HTTP_PROXY / HTTPS_PROXY 环境变量），无需额外设置。直链下载用 <code>requests.Session(trust_env=True)</code> 尊重系统代理。</p><p><strong>Apify 模式</strong>：Instagram 下载也可走 Apify 代理（详见下一条），但 Apify API 服务器和 CDN 都在境外，仍需代理。</p>',
    'faq.a9': '<p>Apify 是第三方爬虫代理平台，Lumio 通过它提取 Instagram 数据，<strong>替代直接调用 IG 移动 API，避免账号风控</strong>。Token 是免费的，个人使用足够。</p><p><strong>获取步骤：</strong></p><ol><li>注册 Apify 账号：<a href="https://console.apify.io/sign-up" target="_blank" rel="noopener" class="faq-link">console.apify.io/sign-up</a>（注意是 .io 不是 .com）</li><li>登录后进入 Console → 右上角 <strong>Settings</strong> → <strong>Integrations</strong> 页面</li><li>复制 <strong>Your API token</strong>（格式 <code>apify_api_xxxxxxxxxxxx</code>）</li><li>在 Lumio Settings 页面「Cookie/API 凭证管理」区粘贴 Token</li><li>Actor ID 默认填 <code>shu8hvrXbJbY3Eb9W</code>（Instagram Scraper 官方 Actor）</li><li>点「验证连接」即可启用</li></ol><p><strong>免费额度：</strong>Apify 每月提供 <strong>$5 免费额度</strong>，个人使用足够。用量在 <a href="https://console.apify.io" target="_blank" rel="noopener" class="faq-link">console.apify.io</a> 首页查看。</p><p><strong>注意：</strong>Apify API 服务器（<code>api.apify.com</code>）和媒体 CDN 都在境外，国内网络需挂代理才能解析和下载成功。</p><p><strong>官网域名：</strong>主站 <a href="https://apify.com" target="_blank" rel="noopener" class="faq-link">apify.com</a>，控制台 <code>console.apify.io</code>，文档 <code>docs.apify.com</code>。</p>',
    'faq.a10': '<p>Lumio <strong>内置预览</strong>支持图片缩放、多图切换、视频/音频播放（QMediaPlayer），点击缩略图即可打开，无需切窗口。</p><p>但下载的 HEVC/H.265、4K HDR、特殊编码格式，建议安装<strong>专用播放器</strong>获得最佳体验：</p><ul><li><strong>PotPlayer</strong>（推荐，Windows）—— <a href="https://potplayer.tv/" target="_blank" rel="noopener" class="faq-link">potplayer.tv</a>，解码器全，支持硬解</li><li><strong>VLC</strong>（跨平台）—— <a href="https://www.videolan.org/" target="_blank" rel="noopener" class="faq-link">videolan.org</a>，Windows / macOS / Linux 通吃</li><li><strong>mpv</strong>（极客向）—— <a href="https://mpv.io/" target="_blank" rel="noopener" class="faq-link">mpv.io</a>，轻量、命令行友好、画质调校强</li></ul><p><strong>在 Lumio 中使用外部播放器：</strong>Library 素材库中双击素材，会用系统默认播放器打开。可在系统设置中把视频默认程序改为 PotPlayer / VLC / mpv。</p>',

    // ─── 截图/浏览器框/视频（P2 补全）───
    'meta.title': 'Lumio — 个人媒体库 · 收藏互联网喜欢的一切',
    'platforms.visit': '访问 {name} 官网',
    'img.alt.home': 'Lumio 主页 — 链接解析',
    'img.alt.player': 'Lumio 内部播放器 — 原画质播放',
    'img.alt.extension': 'Lumio 浏览器扩展 — 右键发送到 Inbox',
    'img.alt.library': 'Lumio 媒体库 — 缩略图网格 + 搜索 + 分类',
    'chrome.home': 'Lumio · Home',
    'chrome.player': 'Lumio · 内部播放器',
    'chrome.extension': 'Lumio · 浏览器插件',
    'chrome.library': 'Lumio · 媒体库',
    'chrome.demo1': 'lumio · 解析全链路',
    'chrome.demo2': 'lumio · 浏览器插件发送',
    'demo.01.video': '链接解析全过程演示',
    'demo.02.video': '浏览器插件发送演示',

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
    'platforms.cnFriendly': 'Works in mainland China: Weibo / Xiaohongshu / Douyin / Bilibili / Kuaishou are all supported — no VPN required, runs locally out of the box.',

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
    'faq.a1': '<p>No. Lumio is a purely local tool — no registration, no login. Downloading Instagram content requires importing your IG cookies (Netscape format); downloading X images and batch enumeration requires your auth_token + ct0 cookies. The other 6 platforms (YouTube / Bilibili / Douyin / Kuaishou / Weibo / Xiaohongshu) work out of the box with no credentials.</p>',
    'faq.a2': '<p>Yes. Every platform downloads the highest quality tier its API offers:</p><ul><li><strong>YouTube</strong>: 4K / 8K + automatic audio merge (you pick the format manually)</li><li><strong>Instagram</strong>: videos take the largest-width rendition, images take the largest entry in image_versions2.candidates</li><li><strong>X (Twitter)</strong>: images fetched as originals (?format=jpg&name=orig), videos take the highest bitrate</li><li><strong>Bilibili</strong>: DASH fnval=16 + qn=127 + fourk=1 requests the top tier</li><li><strong>Douyin</strong>: iterates bit_rate[] in the aweme detail API and takes the highest (known limit: 60fps H.265 ultra-HD originals require the app API)</li><li><strong>Weibo / Xiaohongshu / Kuaishou</strong>: highest resolution returned by the API</li></ul><p>All downloads are free of platform watermarks.</p>',
    'faq.a3': '<p>Lumio is designed to avoid triggering anti-bot measures:</p><ul><li><strong>Instagram</strong>: the browser extension injects once to extract direct links from the DOM when you right-click an IG page — no IG API calls, no automation detection</li><li><strong>X</strong>: uses the GraphQL API with your cookies, at a restrained pace, no mass scraping</li><li><strong>Douyin</strong>: automatically obtains the ttwid visitor identifier — no user cookies or a_bogus signing needed</li><li><strong>Batch downloads</strong>: built-in exponential-backoff retries (5s → 15s → 30s) to keep a polite pace</li></ul><p>That said, please use it reasonably — avoid downloading hundreds of items in a short burst.</p>',
    'faq.a4': '<p>Yes. Installers for all three platforms are built and published automatically via GitHub Actions — click "Download Lumio" on the homepage and pick yours:</p><ul><li><strong>Windows</strong>: NSIS installer (custom install path + clean uninstall)</li><li><strong>macOS</strong>: DMG (separate x64 / arm64 builds)</li><li><strong>Linux</strong>: AppImage / .deb / .rpm</li></ul><p>For users in China, the download dialog defaults to the Cloudflare CDN mirror — no proxy needed.</p>',
    'faq.a5': '<p>Everything is stored locally — nothing is uploaded to any server:</p><ul><li><strong>Media library</strong>: ~/.lumio/library.db (SQLite, metadata + content_hash)</li><li><strong>Download history</strong>: ~/.lumio/history.json</li><li><strong>Config</strong>: ~/.lumio/config.json</li><li><strong>Download queue</strong>: ~/.lumio/queue.json (atomic writes, crash-safe)</li><li><strong>Media files</strong>: your chosen directory, auto-indexed into the library</li></ul><p>Lumio collects no user data and sends no telemetry. Deleting ~/.lumio/ wipes everything.</p>',
    'faq.a6': '<p>The Chrome / Edge extension (Manifest V3) works like this:</p><ol><li>Open the Lumio extension on a social media detail page</li><li>The extension automatically parses and extracts the page\'s media metadata</li><li>One click sends it to the Inbox</li></ol><p>Security:</p><ul><li>The extension only reads page DOM metadata — never your DMs or chats</li><li>Data goes to the desktop app via the local API (127.0.0.1:38900), never through an external server</li><li>For IG it injects once to extract direct links — no persistent content script, no IG API calls</li><li>Open source — audit it yourself</li></ul>',
    'faq.a7': '<p>Lumio is <strong>MIT-licensed open source</strong>, completely free with no paid features. Source code is hosted on <a href="https://github.com/Roseannepark0211/Lumio" target="_blank" rel="noopener" class="faq-link">GitHub</a> — Stars / Issues / PRs welcome.</p>',
    'faq.a8': '<p><strong>It depends on the platform:</strong></p><ul><li><strong>Chinese platforms</strong> (Weibo / Xiaohongshu / Douyin / Bilibili / Kuaishou) — no proxy needed, just works.</li><li><strong>Foreign platforms</strong> (YouTube / Instagram / X) — you\'ll need your own proxy tool from mainland China.</li></ul><p>On startup, Lumio probes external connectivity (tries youtube.com:443) and notifies you if it\'s unreachable.</p><p><strong>Proxy setup:</strong> Lumio automatically picks up your system proxy (HTTP_PROXY / HTTPS_PROXY environment variables) — no extra configuration. Direct-link downloads use <code>requests.Session(trust_env=True)</code>, which honors the system proxy.</p><p><strong>Apify mode</strong>: Instagram downloads can also go through the Apify proxy (see the next question), but Apify\'s API servers and CDNs are all overseas, so a proxy is still required.</p>',
    'faq.a9': '<p>Apify is a third-party scraping proxy platform. Lumio uses it to fetch Instagram data <strong>instead of calling IG\'s mobile API directly, keeping your account safe from flags</strong>. The token is free, and the free tier is plenty for personal use.</p><p><strong>How to get one:</strong></p><ol><li>Sign up for an Apify account: <a href="https://console.apify.io/sign-up" target="_blank" rel="noopener" class="faq-link">console.apify.io/sign-up</a> (note: .io, not .com)</li><li>After logging in, go to Console → <strong>Settings</strong> → <strong>Integrations</strong> (top right)</li><li>Copy <strong>Your API token</strong> (format <code>apify_api_xxxxxxxxxxxx</code>)</li><li>Paste it in Lumio\'s Settings page under "Cookie / API credentials"</li><li>Actor ID defaults to <code>shu8hvrXbJbY3Eb9W</code> (the official Instagram Scraper actor)</li><li>Click "Verify connection" and you\'re set</li></ol><p><strong>Free quota:</strong> Apify gives you <strong>$5 of free credit every month</strong> — plenty for personal use. Check your usage on the <a href="https://console.apify.io" target="_blank" rel="noopener" class="faq-link">console.apify.io</a> homepage.</p><p><strong>Note:</strong> Apify\'s API servers (<code>api.apify.com</code>) and media CDNs are all overseas — you\'ll need a proxy from mainland China for resolving and downloading to succeed.</p><p><strong>Domains:</strong> main site <a href="https://apify.com" target="_blank" rel="noopener" class="faq-link">apify.com</a>, console <code>console.apify.io</code>, docs <code>docs.apify.com</code>.</p>',
    'faq.a10': '<p>Lumio\'s <strong>built-in preview</strong> handles image zoom, multi-image switching, and video/audio playback (QMediaPlayer) — just click a thumbnail, no window switching.</p><p>For HEVC/H.265, 4K HDR, or exotic codecs, though, a <strong>dedicated player</strong> gives a better experience:</p><ul><li><strong>PotPlayer</strong> (recommended, Windows) — <a href="https://potplayer.tv/" target="_blank" rel="noopener" class="faq-link">potplayer.tv</a>, complete codec support with hardware decoding</li><li><strong>VLC</strong> (cross-platform) — <a href="https://www.videolan.org/" target="_blank" rel="noopener" class="faq-link">videolan.org</a>, runs on Windows / macOS / Linux</li><li><strong>mpv</strong> (for geeks) — <a href="https://mpv.io/" target="_blank" rel="noopener" class="faq-link">mpv.io</a>, lightweight, CLI-friendly, great quality tuning</li></ul><p><strong>Using an external player in Lumio:</strong> double-click an item in the Library to open it with your system default player. Set your default video app to PotPlayer / VLC / mpv in system settings.</p>',

    // ─── 截图/浏览器框/视频（P2 补全）───
    'meta.title': 'Lumio — Personal Media Library · Keep Everything You Love',
    'platforms.visit': 'Visit {name} official site',
    'img.alt.home': 'Lumio home — link parsing',
    'img.alt.player': 'Lumio built-in player — original-quality playback',
    'img.alt.extension': 'Lumio browser extension — right-click to send to Inbox',
    'img.alt.library': 'Lumio media library — thumbnail grid + search + collections',
    'chrome.home': 'Lumio · Home',
    'chrome.player': 'Lumio · Player',
    'chrome.extension': 'Lumio · Extension',
    'chrome.library': 'Lumio · Library',
    'chrome.demo1': 'lumio · parse pipeline',
    'chrome.demo2': 'lumio · extension send',
    'demo.01.video': 'Full link-parsing walkthrough',
    'demo.02.video': 'Browser extension send demo',

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
  // 插值：data-i18n-name="xxx" 会替换文案中的 {name}
  document.querySelectorAll<HTMLElement>('[data-i18n-attr]').forEach((el) => {
    const spec = el.dataset.i18nAttr || '';
    const name = el.dataset.i18nName || '';
    spec.split(',').forEach((pair) => {
      const [attr, key] = pair.split(':').map((s) => s.trim());
      if (!attr || !key) return;
      let val = table[key];
      if (val === undefined) return;
      if (name) val = val.replace('{name}', name);
      el.setAttribute(attr, val);
    });
  });

  // 浏览器标签页标题跟随语言
  const pageTitle = table['meta.title'];
  if (pageTitle) document.title = pageTitle;

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
