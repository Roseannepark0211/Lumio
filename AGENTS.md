# Lumio

个人自用桌面工具，通过分享链接下载 YouTube、Instagram、X (Twitter) 及国内主流平台（B站/抖音/快手/微博/小红书）的图片/视频。

## 技术栈

- Python 3.10+ / PySide6 (Qt) — 桌面 GUI
- QML / QtQuick — 前端 UI（V4.3 重构后主界面，替代原 QWidget）
- yt-dlp — YouTube + X (Twitter) 下载（含 ffmpeg 合并视频+音频）
- instaloader — Instagram 下载（图片+视频+轮播帖，逐步弃用，改用浏览器直链）
- Flask — 本地 API 服务（127.0.0.1:38900），接收浏览器扩展采集内容
- imageio-ffmpeg — 内置 ffmpeg 二进制，无需系统安装
- SQLAlchemy — 素材库 + 收件箱 ORM（~/.lumio/library.db）
- Pillow — 缩略图生成（图片缩放）
- python-telegram-bot — Telegram Bot 轮询服务，接收用户发送的内容写入 Inbox
- apify-client — Apify Actor 代理，替代直接 IG 移动 API 调用，避免账号风险
- 中/英双语（i18n），设置页面切换

## 快速开始

```powershell
pip install -e .
python -m lumio.main
```

## 项目结构

```
src/lumio/
  __init__.py         — 版本号 __version__
  main.py             — 入口（QApplication + 组件装配 + QML 启动）
  downloader.py       — 下载引擎（yt-dlp[YouTube/X视频] + GraphQL API[X图片/批量] + 直链下载[IG/通用]）
  queue_manager.py    — 下载队列管理（单任务/批量/暂停/重试/恢复/错误分类/原子写入）
  history_manager.py  — 下载历史记录（JSON 持久化，~/.lumio/history.json）
  library_manager.py  — 素材库管理（SQLAlchemy/SQLite，~/.lumio/library.db）
  inbox_manager.py    — 收件箱管理（SQLAlchemy/SQLite 持久化；接收浏览器扩展 + Telegram Bot 采集内容）
  notification_manager.py — 通知管理（环境检测 + 版本检查 + JSON 持久化，threading.RLock 防自死锁）
  api_server.py       — 本地 Flask API（127.0.0.1:38900，/health + /capture，make_server 优雅释放端口）
  telegram_service.py — Telegram Bot 轮询服务，接收用户发送的内容写入 Inbox
  apify_client.py     — Apify Actor 代理，替代直接 IG 移动 API 调用
  x_sou_client.py     — X-Sou 搜索 API 客户端
  thumbnail_engine.py — 缩略图生成（Pillow 图片缩放 + ffmpeg 视频截帧）
  models.py           — SQLAlchemy ORM 模型（LibraryItem/Collection/ItemCollection/InboxItem）
  i18n.py             — 中/英翻译字典（延迟加载，首次 t() 时读 config）
  assets/
    logo.png          — 应用图标（窗口 + 任务栏）

  qml/                — QML 前端（V4.3 主 UI）
    Main.qml          — QML 根（QQmlApplicationEngine 加载）
    Theme.qml         — 主题常量（颜色/字号/圆角/字体，平台标签中文/字母映射）
    Lumio/
      Theme.qml
      qmldir
      Assets/
        icons.svg     — 单文件 SVG symbol 集（image://icons/ 协议渲染）
        reference.css
      Components/     — 复用组件
        Badge.qml / Button.qml / GlassCard.qml / Icon.qml / Input.qml
        LaserProgressBar.qml / LumioComboBox.qml / LumioSpinBox.qml
        PageHeader.qml / Pill.qml / SettingsCard.qml / Sidebar.qml
        Textarea.qml / VideoPreviewDialog.qml / qmldir
      Pages/          — 8 个页面
        HomePage.qml       — URL 输入→解析→预览→加入队列；X-Sou 搜索；多行批量导入
        InboxPage.qml      — 收件箱（采集内容列表 + 格式选择 + 批量下载）
        DownloadsPage.qml  — 下载队列管理 + 任务卡片 + 全局操作
        HistoryPage.qml    — 下载历史列表 + 搜索 + 平台筛选 + 批次分组折叠
        LibraryPage.qml    — 素材库：搜索/筛选/分类/收藏/列表/批量操作
        StatsPage.qml      — 统计卡片 4+3 布局
        NotificationsPage.qml — 通知页面（环境/依赖/版本通知 + 分类筛选 + 永久通知）
        SettingsPage.qml   — 分组设置（通用/下载/Cookie/缓存/About）

  gui/                — Python 侧 GUI 支持层（QML 迁移后大部分 QWidget 已废弃）
    qml_bridge.py     — QML 桥接层（QmlController：暴露后端能力给 QML，含 IconProvider/ThumbProvider）
    cookie_checker.py — Cookie 有效性检测（返回 missing/expired/warning/valid 枚举）
    # 以下为旧 QWidget 版本文件，QML 版已弃用，仅供历史参考：
    # window.py / sidebar.py / home_page.py / home_page_new.py / downloads_page.py
    # history_page.py / library_page.py / stats_page.py / settings_page.py
    # inbox_page.py / notification_page.py / format_dialog.py / profile_dialog.py
    # yt_dialog.py / x_dialog.py / domestic_dialog.py / queue_panel.py
    # history_panel.py / library_panel.py / preview_dialog.py / settings.py
    # styles.py / widgets.py / icon_provider.py

  utils/
    url_parser.py    — URL 平台识别（YouTube / Instagram / X / 国内平台 / 不支持）
    config.py        — 配置读写（~/.lumio/config.json + history.json 路径，内存缓存）
    database.py      — SQLAlchemy 引擎 + session 工厂
    media_utils.py   — 媒体类型推断 + format_size 工具
    error_types.py   — 下载错误分类（Cookie/网络/限流/内容/解析）
    cache_manager.py — 缓存管理（统计/手动/定时清理 inbox_media/thumbs/provider_cache/preview）

  providers/
    base.py          — Provider 抽象基类（Platform/BaseProvider/MediaInfo/MediaItem/FormatOption）
    registry.py      — Provider 注册表（手动注册 + 自动发现；get_provider 优先 match() 再回退 detect_domestic）
    dispatch.py      — Provider 调度桥接（URL → MediaInfo → VideoInfo，统一所有平台入口）
    detector.py      — 国内平台 URL 识别（正则匹配 + 回退 url_parser）
    url_normalizer.py— URL 规范化（短链展开：t.cn/b23.tv/xhslink.com/xhslink.cn/iesdouyin.com/v.douyin.com）
    cache.py         — URL → MediaInfo 两级缓存（内存 TTL + 文件 JSON 持久化）
    bilibili.py      — B站 Provider（BV/av 号 + b23.tv 短链，DASH fnval=16）
    douyin.py        — 抖音 Provider（视频多清晰度 + 图文帖 note + 短链 + a_bogus 签名服务可选增强）
    kuaishou.py      — 快手 Provider（视频解析）
    weibo.py         — 微博 Provider（图片/视频/livephoto/mix_media_info 多图轮播/转发，sinaimg.cn CDN 需 Cookie + Referer）
    xiaohongshu.py   — 小红书 Provider（图片/视频笔记 + xhslink.com/xhslink.cn 短链 + HTML __INITIAL_STATE__ 抓取）
    youtube.py       — YouTube Provider（包装 yt-dlp extract_info + FormatOption 构建）
    instagram.py     — Instagram Provider（cookie 模式调移动 API，取最高画质直链，复现 saveinta.com 服务端机制）
    x.py             — X (Twitter) Provider（GraphQL API 提取图片/视频，单视频推文附加 yt-dlp formats）
    network/         — 网络层（client/headers/cookie/retry）
    exceptions.py    — Provider 异常类

extension/             — Chrome/Edge 浏览器扩展（Manifest V3）
  manifest.json        — 扩展配置（permissions: activeTab/tabs/contextMenus/scripting/storage/notifications）
  background.js        — Service Worker（右键菜单 + 一次性 IG 注入 + 发送到 API）
  content.js           — Content Script（YouTube/X 页面元数据提取，IG 不常驻注入）
  ig_extract.js        — IG 一次性提取脚本（读取 DOM 媒体 URL，不调 IG API）
  popup.html/js        — 弹窗（连接状态 + 手动发送 + 最近历史）
  icons/               — 扩展图标（16/48/128）

tests/
  test_url_parser.py          — URL 解析单测（22 cases）
  test_download_pipeline.py   — 下载链路测试（47+ cases）
  test_integration.py         — 集成测试（真实网络：IG/YT/X，15 cases）
  test_bilibili_provider.py   — B站 Provider 单测（27 cases）
  test_douyin_provider.py     — 抖音 Provider 单测
  test_kuaishou_provider.py   — 快手 Provider 单测
  test_weibo_provider.py      — 微博 Provider 单测（多图/视频/livephoto/转发/URL 检测）
  test_xiaohongshu_provider.py — 小红书 Provider 单测
  test_providers.py           — Provider 注册/调度通用单测
  test_library_manager.py     — 素材库 ORM 单测
  test_history_manager.py     — 历史记录单测
  test_queue_task.py          — 队列任务单测
  test_media_utils.py         — 媒体工具单测
  test_config.py              — 配置读写单测
  test_error_types.py         — 错误分类单测
```

## 运行验证

```powershell
# 单测（忽略需要真实网络的集成测试）
PYTHONPATH=src python -m pytest tests/ -v --ignore=tests/test_integration.py

# 启动 GUI
python -m lumio.main
```

## Release 规范

每次发布新版本必须在 GitHub Release 中写明更新内容，格式：

```markdown
## ✨ 新功能
- 功能描述

## 🐛 Bug 修复
- 修复描述

## ⚠️ 已知问题
- 问题描述（如有）

## 📦 安装说明
（首次发布写完整说明，后续版本只写关键变更）
```

要求：
- 每条变更一行，简洁明了
- 新功能和修复按影响程度排序（重要的在前）
- 涉及 API/行为变更的必须标注
- 浏览器扩展如有更新，单独列出版本号

## 关键行为

### UI / 页面

- **Sidebar 导航**：左侧固定导航栏，8 个页面（Home/Inbox/Downloads/History/Library/Stats/Notifications/Settings），含红点徽章（1-9 圆点 / 10-99 胶囊 / ≥100 显示 99+）
- **Home 页面**：仅负责 URL 解析 + 预览 + 加入队列；支持多行 URL 批量导入；入队前自动去重检查；预览区比例自适应（横屏 16:9 / 正方形 1:1 / 竖屏 9:16）
- **Downloads 页面**：独立全页面管理下载队列，含任务卡片 + 全局操作（全部开始/暂停/继续/全部恢复/清空）
- **History 页面**：独立全页面，含搜索框 + 平台筛选下拉 + 记录卡片（打开文件/目录/删除）；按 batch_id 分组折叠展示
- **Library 页面**：素材库，下载自动入库；缩略图预览（点击打开内置预览）、素材预览（图片缩放/多图切换、视频/音频播放器）、Collections 分类系统、收藏、多维搜索筛选（文本+平台+类型+收藏+日期范围+批次）+ 一键重置；批量操作含「全选/取消全选」+ 批量收藏/删除/加入 Collection；右上角统计 badge 用 Layout.preferredWidth 自适应防溢出
- **Stats 页面**：统计卡片 4+3 布局展示总下载数、总下载体积、成功率、今日下载、各平台数量
- **Settings 页面**：分组设置（通用/下载/Cookie/缓存/About）；Cookie/API 凭证管理区用 QToolButton 可折叠（默认折叠，已配置 cookie 或处于 API 模式则默认展开）；ScrollView contentWidth 必须绑定 width 防内容被挤压
- **Notifications 页面**：环境/依赖/版本通知 + 分类筛选 + 永久通知（如 IG 风险提示、VPN/代理、媒体播放器推荐）

### 平台支持

- **平台自动识别**：粘贴链接即识别 YouTube/Instagram/X/B站/抖音/快手/微博/小红书，无需手动选
- **V4 统一架构**：所有平台（含 YouTube/Instagram/X）均走 Provider 系统；`downloader.extract_info()` 统一调 `resolve_via_providers()`；`get_provider()` 优先遍历已注册 Provider 的 `match()`，再回退到 `detect_domestic()` 识别国内平台
- **YouTube**：YouTubeProvider 包装 yt-dlp `extract_info`，构建 `FormatOption` 列表供 Home 格式选择；下载走 yt-dlp 路径，纯视频自动合并音频，纯音频自动合并视频
- **Instagram**：复现 saveinta.com 服务端机制——用户导入 cookie 调 `i.instagram.com/api/v1/media/{id}/info/` 移动 API，直接拿 IG CDN 直链；视频取 `video_versions` 中 width 最大档位，图片取 `image_versions2.candidates` 中 width 最大档位；下载直接平铺到 output_dir，文件名含 author_postTime 确保唯一；取消时自动清理部分写入文件
- **Instagram 安全下载**：右键 IG 页面时浏览器扩展一次性注入 `ig_extract.js`，从 DOM 读取 `<video src>` / `og:image` / `og:video` 提取直链；Lumio 用 `_direct_download_with_pause` 直接从 CDN 下载，不调用 IG API
- **X (Twitter)**：XProvider 走 GraphQL API 提取图片原图（`?format=jpg&name=orig`）+ 视频最高 bitrate；单视频推文附加 yt-dlp formats 供格式选择；图片下载和批量枚举需 `auth_token` + `ct0` cookies
- **X-Sou 搜索**：Home 页面搜索按钮（设置页可开关，默认关闭含 18+ 警告），调 X-Sou API（`/api/search?q=关键词`）；结果列表含缩略图+预览+分页+勾选入队；`@username` 自动转 `from:username` 搜索
- **X-Sou 下载**：搜索结果 `video_url` 已是 Twitter CDN 直链（`video.twimg.com`，永久有效），直接作为 `direct_url` 入队跳过 X GraphQL 流程；下载走通用直链路径，自动用 `requests.Session(trust_env=True)` 尊重系统代理；`task.url` 记录推文 URL 仅用于历史/去重
- **B站**：BV/av 号 + b23.tv 短链；DASH 接口 `fnval=16`（注意：`fnval=404` 会被 web API 拒绝 code=-400）；`qn=127` + `fourk=1` 请求最高档，服务端按账号权限降级
- **抖音**：调 aweme detail API 遍历 `bit_rate[]` 数组提取所有档位；自动获取 ttwid 访客标识，无需用户 cookie；可选 a_bogus 签名服务（localhost:9528，Playwright 实现）拿更多 H.265 档位；图文帖 `douyin.com/note/{id}` 与视频共用同一 API
- **抖音清晰度**：从 `gear_name` 提取真实短边分辨率（如 `normal_1080_0` → 1080p），不用竖屏 `play_addr.height` 长边；MediaItem.width/height 用 API 真实像素（供 QML 宽高比计算），quality 字段存清晰度标签，FormatOption.height 用 res_num 供格式下拉显示
- **抖音图文帖**：detector.py 必须同时包含 `note/(\d+)` 模式，否则短链展开后识别失败
- **快手**：短视频解析下载
- **微博**：图片/视频/livephoto/mix_media_info 多图轮播/转发；livephoto 必须用完整 play 页 URL（`video.weibo.com/media/play?livephoto=...`）而非 CDN 直链避免 403；sinaimg.cn 需 Cookie（SUB/SUBP）+ Referer
- **小红书**：图片/视频笔记 + xhslink.com/xhslink.cn 短链；旧 API `/api/sns/v1/note/{id}` 已下线，改用 HTML 抓取 `__INITIAL_STATE__`；字段从 snake_case 改为 camelCase；需从 URL 提取 `xsec_token` + `xsec_source` 附加到查询参数
- **小红书图片 URL 选取**：`urlDefault`（WB_DFT 场景）可直接下载优先用；`url` 原图为最高优先级但部分笔记为空；`urlPre` 是预览图画质低兜底用
- **国内平台短链**：t.cn/b23.tv/xhslink.com/xhslink.cn/iesdouyin.com/v.douyin.com 自动展开；URL → MediaInfo 两级缓存（内存+文件）
- **直链下载**：`direct_url` 优先级高于平台路由，`start_download_with_pause` 检测到 `direct_url` 时走通用下载路径，跳过 yt-dlp/instaloader/GraphQL

### 下载与队列

- **文件名**：默认用作者名+发布时间戳；可手动修改；轮播帖自动编号
- **文件名安全**：`custom_name` 经 `_safe_filename()` 清洗，去掉 `\/:*?"<>|` 和 `..` 防路径穿越
- **文件冲突策略**：config `file_conflict_policy` 控制重复下载行为（rename/skip/overwrite），默认 rename 自动加 `(1)` 后缀；IG 用 `_resolve_conflict_path()`，YT/X 用 `_resolve_conflict_stem()` 匹配 `stem.*`
- **队列行为**：单任务"开始"只启动该任务；"全部开始"和 retry 均按 max_workers 并发上限调度；任务完成后不自动启动下一个
- **智能重试**：失败后指数退避重试（5s→15s→30s），UI 显示"重试中 (N/3)"状态；TaskStatus 含 RETRYING/INTERRUPTED
- **错误分类**：downloader 异常自动分类为 Cookie/网络/限流/内容/解析错误，UI 显示友好提示（error_types.py）
- **断点续传**：yt-dlp 启用 `continuedl=True` + `keep_fragments=True`；downloader 直链下载支持 Range header + append 模式，异常时不再删除 partial 文件；YouTube/X 中断后可续传（Instagram 因 instaloader 限制不支持）
- **任务恢复**：app 重启后 DOWNLOADING 任务自动标记为 INTERRUPTED，支持"全部恢复"
- **下载去重**：入队前检查 Library URL 是否已存在，重复时提示"仍然下载？"
- **多流下载进度**：yt-dlp 多流（视频+音频）下载 `finished` hook 触发两次，downloader 跟踪多流状态累计进度，统一在末流完成时标记 done
- **队列线程安全**：queue_manager 所有公开方法对 `_tasks`/`_active` 统一加锁；`threading.Lock` 不可重入，持锁方法不能调用其他获锁方法（否则死锁），Signal 必须在锁外发射；pause_event.wait() 用 100ms 超时循环而非阻塞
- **队列原子写入**：queue.json 写入时先写临时文件再 `os.replace` 原子替换，防止崩溃截断
- **媒体类型标注**：下载队列、历史记录和素材库中统一标注 Video/Audio/Image/Mixed

### 批量下载

- **批量导入**：Home 页面粘贴多行 URL，确认后逐个解析+入队
- **Instagram 批量**：粘贴 @用户名 或主页链接，弹出批量对话框；完成后自动跳转 Downloads 页面
- **YouTube 批量**：粘贴频道/播放列表链接，弹出批量对话框；完成后自动跳转 Downloads 页面
- **X (Twitter) 批量**：粘贴 @用户名 或主页链接，弹出批量对话框；仅枚举含媒体（图片+视频）的推文；需 `auth_token` + `ct0` cookies
- **History 批次聚合**：批量下载共享 `batch_id`，History 页面按 batch_id 分组折叠展示

### 收件箱 / 通知 / 系统

- **Inbox 收件箱**：SQLAlchemy/SQLite 持久化（~/.lumio/library.db 的 inbox_items 表）；数据源为浏览器扩展（POST /capture）和 Telegram Bot；支持 URL/直链/图片/视频/文件/笔记/相册等类型；每条记录带 source（browser/telegram）、platform、post_time、duration 元数据；支持格式选择（单个）/ 最高画质（批量）；图片类型跳过格式选择；元数据不足时自动 `extract_info` 补全；默认筛选「新内容」
- **通知系统**：sidebar 独立页面（🔔），JSON 持久化（~/.lumio/notifications.json）；三类标签（依赖/环境/版本更新）；永久通知（IG 风险提示 + 系统级 VPN/代理/媒体播放器/Telegram Bot/Apify Token 推荐，不可关闭）；启动时自动检测 Cookie/FFmpeg/插件提示
- **版本检查**：Settings About 区域「检查更新」按钮，git fetch + 语义版本对比（7 天间隔），结果写入通知
- **系统托盘**：关闭窗口弹出三选（最小化到托盘 / 退出 / 取消）；托盘图标右键菜单（显示窗口 / 退出）；`setQuitOnLastWindowClosed(False)` 保持后台运行；closeEvent 中 `QTimer.singleShot(0, quit)` 显式退出事件循环
- **Local API Server**：Flask daemon thread，`make_server` + `shutdown()` 优雅释放端口；`/health` 日志过滤；接收浏览器扩展 POST /capture
- **浏览器扩展**：Manifest V3，Chrome/Edge 共用；右键菜单发送页面/链接/视频/图片；content.js 提取 YouTube/X 元数据；IG 不常驻注入
- **Telegram Bot 服务**：`telegram_service.py` 轮询 Bot API，接收用户发送的链接/媒体/笔记/相册，自动下载媒体到 `~/.lumio/inbox_media/` 并写入 Inbox 收件箱；支持多设备绑定（配对码机制）；所有 Telegram 媒体项 platform=telegram；媒体组聚合为一个 InboxItem 指向组文件夹；支持本地 Bot API Server（突破 20MB 限制，Settings 页面「API 地址」配置）
- **Apify IG 代理**：`apify_client.py` 通过 Apify Actor 代理提取 Instagram 数据，替代直接调用 IG 移动 API，避免账号风控；提供 `extract_post_info`、`fetch_profile_info`、`enumerate_profile_posts` 等接口
- **缓存管理**：`utils/cache_manager.py` 统一管理 4 个缓存目录（inbox_media/thumbs/provider_cache/preview）；Settings 页面「缓存管理」分组展示各目录大小+文件数、提供「立即清理」按钮（后台线程执行）、自动清理模式选择（关闭/每次启动/每天/每周）、保留天数与单目录上限配置；启动时根据 `config.cache_management.auto_clean` 后台触发自动清理（不阻塞启动）；清理策略=保留最近 N 天 + 超上限按 mtime 删最旧；安全白名单扩展名（图片/视频/音频/json/tmp）；下载历史/素材库/cookies/config 等用户数据不在清理范围

### 素材库 / 元数据

- **素材预览**：点击缩略图打开内置预览；图片支持缩放/平移/多图左右切换；视频/音频用 QMediaPlayer + 自定义控制栏；目录路径自动扫描首个媒体文件；不支持格式显示错误提示
- **收藏按钮**：`setCheckable(True)` + `setChecked()` 激活 stylesheet `:checked` 红色，未收藏灰色空心
- **media_type 推断**：`add_item` 优先用文件路径推断（扩展名/目录内容），不依赖预设值；启动时 `_backfill_media_types()` 纠正历史错误记录
- **缩略图补生成**：启动时 `backfill_thumbnails()` 自动为缺失缩略图的素材后台生成 + `thumbnail_updated` 信号刷新 UI
- **Collection sidebar**：显示每个 Collection 的素材数量；右键菜单支持重命名/删除；`collection_changed` 信号驱动统计刷新；菜单用 `btn.mapToGlobal(pos)` 而非 `self.sender().mapToGlobal(pos)`
- **Library 批量全选**：「全选/取消全选」按钮通过 `LibraryPanelCard.setChecked()` 程序化触发 checkbox
- **content_hash**：入库时自动计算文件内容 hash（图片全 MD5 / 视频音频首 1MB+size）；启动时 `backfill_hashes()` 补算历史记录
- **搜索范围**：History 和 Library 搜索均覆盖 title/author/url/file_path/post_time，大小写不敏感（ILIKE / .lower()）
- **Library 日期过滤**：需兼容空 `post_time`（`OR post_time == ""`），否则 X 等平台下载被过滤掉

### 配置 / 国际化

- **配置缓存**：config.py 首次读磁盘后缓存到内存，`save_config` 同步更新缓存
- **i18n 延迟加载**：语言配置在首次 `t()` 调用时才从 config 读取，不在 import 时
- **语言切换**：设置页面选择中/英，确认后立即重启生效
- **Light/Dark 主题**：侧边栏底部切换按钮，主题选择持久化到 config.json；切换时需 unpolish/polish 强制刷新所有子 widget
- **Cookie 导入**：合并模式（按 `domain+name` 去重），不再 `shutil.copy2` 覆盖；多平台 cookie 可共存于同一文件
- **Cookie 检测**：cookie_checker.py 返回枚举值（`missing`/`expired`/`warning`/`valid`），不返回中文字符串
- **ffmpeg**：通过 imageio-ffmpeg 内置，二进制名 `ffmpeg-win-x86_64-v7.1.exe`
- **版本号**：`__version__` 定义在 `__init__.py`，sidebar 和 settings 统一引用
- **缩略图异步**：Home 页面缩略图通过 `_ThumbWorker(QThread)` 后台拉取，不阻塞 GUI 线程
- **ComboBox 滚轮**：Settings/Home/YT Dialog 的选择器用 `NoWheelComboBox` 禁用滚轮防误触；History/Library 的筛选器保留滚轮

## 踩坑记录

### yt-dlp / ffmpeg

- yt-dlp 的 `ffmpeg_location` 必须指向**完整二进制路径**，不能只给目录（二进制名非标准）
- yt-dlp hook 在 `status="finished"` 时就标记 done（rename 前），Windows 上 rename 可能失败；下载后需验证输出文件存在才入库
- yt-dlp 的 TwitterIE 故意过滤掉图片推文（`type != 'photo'`），X 图片下载必须走 GraphQL API
- yt-dlp 多流下载（视频+音频）`finished` hook 触发两次，必须跟踪多流状态累计进度，否则进度条 100% 后又归 0
- Instagram 轮播帖中 yt-dlp 不支持图片，需用 instaloader 处理
- 代理环境下 Instagram 请求偶发 SSL 错误，instaloader 内建重试机制可自愈

### PySide6 / QML

- PySide6 跨线程操作 GUI 控件会崩溃，必须用 Signal/Slot 机制
- PySide6 的 `QUrl` 在 `PySide6.QtCore` 不在 `PySide6.QtGui`，import 写错会 ImportError
- `setQuitOnLastWindowClosed(False)` 导致关闭窗口后 QApplication 不退出；closeEvent 中需 `QTimer.singleShot(0, quit)` 显式退出事件循环
- Qt 样式表的 `background-color` 不会级联到无样式的子 widget viewport；需要用 `QScrollArea > QWidget > QWidget` 精准定位滚动区域背景，不能在 `QWidget` 全局规则上设 background-color
- QML `ScrollView` 必须绑定 `contentWidth: availableWidth`，否则 ColumnLayout 内容会被压缩到 300px 宽
- QML RowLayout 中子项按 `implicitWidth` + `Layout.*` 分配宽度，Rectangle 默认 `implicitWidth=0` 会被挤压；宽度变化的内容必须用 `Layout.preferredWidth` + `Layout.minimumWidth` 而非 `width`
- QML `QClipboard.text` 未暴露为 Q_PROPERTY，QML 无法直接读 `Qt.application.clipboard.text`，必须走 controller Slot
- QML `var` 属性对相同引用的对象不触发 change 信号，mutate 时必须创建新对象
- QML `QMenu.exec()` 在 lambda 上下文中调用 `self.sender()` 返回 None；必须把按钮作为参数传入 lambda，用 `btn.mapToGlobal(pos)`

### Instagram / X

- Instagram 移动端 API 有 429 限流，downloader 内建指数退避重试（5s/15s/30s）；批量枚举时需控制节奏
- Instagram 移动端 API 有自动化检测，频繁调用会导致账号受限/封禁；IG 下载改用浏览器一次性注入提取直链，不调用 IG API
- Instagram URL 解析时自动 strip query/fragment，避免 `?utm_source=...` 混入下载逻辑
- SaveInsta 方案核心 = Lumio cookie 模式：用户 cookie + 移动 API + CDN 直链；不需要 JWT/代理/cftoken 校验
- X 视频 duration 返回 float，GUI 显示时需 `int()` 转换，否则 `:02d` 格式化报错
- X GraphQL API query ID 会定期轮换，当前硬编码在 downloader.py 顶部（`_X_GRAPHQL_TWEET` / `_X_GRAPHQL_USER` / `_X_GRAPHQL_USER_TWEETS`），如果 422 报错需要从 yt-dlp 源码更新
- X v1.1 API（`statuses/show.json`、`users/show.json`）已对 guest token 返回 404，必须用 GraphQL API + auth cookie
- X-Sou API 返回的 `video_url` 部分 403（被封禁账号），不能作为可靠下载源；X-Sou 搜索结果入队时走推文 URL + GraphQL API
- `_x_tweet_id_from_url` 必须先去掉 query/fragment（`?s=20` 等），否则 API 查不到推文
- `_direct_download_with_pause` 必须用 `requests.Session(trust_env=True)` 而非 `requests.get`，否则不会读取系统代理
- X-Sou `video_url` 来自 `video.twimg.com`（公开链接），永不过期，不需要 Referer/Cookie 鉴权；在中国大陆被墙需代理

### 抖音 / 小红书 / 微博

- 抖音图文帖（note）短链 `v.douyin.com/xxx` 经 `normalize_url` 302 展开成 `www.douyin.com/note/{id}`，但 `detector.py` 早期只匹配 `video/`/`user/`/`iesdouyin/`/`v.douyin/`，**必须同时加 `note/(\d+)` 模式**否则识别失败
- 抖音竖屏视频 `play_addr.height` 是长边（1920/1440/960/768），不能直接用作分辨率标签，必须从 `gear_name` 提取真实短边分辨率
- 抖音 MediaItem.width/height 必须用 API 真实像素（如 1080×1920），不能用 res_num（如 1080），否则 QML 宽高比计算错误导致预览黑边
- 抖音 share 页 HTML 仅提供单档 720p，必须调 aweme detail API 拿多清晰度（最高 1440p）；超高清原画档需 app API 或登录态，web API 即使 a_bogus 签名也拿不到（已知限制）
- 抖音 `aweme detail` API 在某些情况下需要 a_bogus 签名才能拿全档位；签名服务不可用时回退到无签名 API（仍可用但档位少）
- 微博 livephoto 直链 CDN（如 `livephoto.us.sinaimg.cn`）返回 403，必须用完整 play 页 URL + Cookie + Referer
- 小红书 PC 分享链接需从含中文描述的文本中提取纯 URL，排除空格/中文/全角字符
- 小红书短链 `xhslink.cn`（新版）需与 `xhslink.com`（旧版）一并加入 `_SHORT_DOMAINS` + `_RESOLVE_DOMAINS`

### SQLAlchemy / Flask

- SQLAlchemy `default=func.now()` 在 SQLite 下只有秒级精度，同秒创建的记录排序不稳定；改用 `default=lambda: datetime.now(timezone.utc)` 获得微秒精度
- SQLAlchemy detached 对象跨方法传递会触发 `DetachedInstanceError`；下载方法统一接收 `item_id: str`，方法内 `get_item(item_id)` 获取新鲜对象
- Flask `app.run()` 不会优雅释放端口；改用 `werkzeug.serving.make_server` + `shutdown()`，确保进程退出后端口立即可用

### 队列 / 锁 / 缓存

- `threading.Lock` 不可重入：`start_task`/`retry_task`/`cancel_task`/`start_all` 等持锁方法不能在锁内调用 `_launch_download()`/`_schedule()`/`_cleanup_task()`，必须先收集工作再释放锁后调用
- NotificationManager 必须用 `threading.RLock()`（可重入锁），否则 `unread_count()` 等方法在持锁方法内调用会自死锁导致通知页卡死
- DownloadManager.resume_task() 对 PAUSED 任务只 `event.set()` 唤醒旧线程，不创建新线程；INTERRUPTED 走 `_schedule()` 重新调度
- pause_event.wait() 必须用 100ms 超时循环而非阻塞，否则 cancel_task 的 event.set() 无法唤醒
- Provider 缓存（~/.lumio/provider_cache/cache.json）按 normalized URL 缓存 MediaInfo；URL 格式/解析逻辑改动后必须清空缓存或重启 app，否则会返回旧数据
- Provider 缓存命中时不调用 `provider.extract_info`；测试时必须在 `setup_method` 中调 `provider_cache.clear_cache()` 避免命中上次测试的缓存

### 文件名 / 杂项

- `_safe_filename()` 会将连续 `..` 替换为 `_`，`file...name` → `file_.name`；只影响文件名 stem，不影响扩展名
- `format_size()` 提取到 `utils/media_utils.py` 作为共享函数，`zero_default` 参数控制零值返回
- VideoPreviewDialog 支持 URL 流式播放（检测 `http/https` 前缀用 `QUrl` 代替 `QUrl.fromLocalFile`）
- `MediaInfo` 的 `author` 是必填字段（无默认值），错误处理分支返回 MediaInfo 时必须传 `author=""`，否则 `TypeError: missing 1 required positional argument: 'author'`
- V4 统一架构后 `downloader.extract_info()` 不再调 `_yt_extract_info`/`_ig_extract_info`/`_x_extract_info`，这些旧函数仅供 Apify/批量子调用；测试 mock 时要 patch `Provider.extract_info` 而非旧函数
- `get_provider()` 优先遍历已注册 Provider 的 `match()` 再回退到 `detect_domestic()`，避免国外平台（YouTube/IG/X）被误判为 UNSUPPORTED
- `LibraryPanelCard` 缺少 `setChecked()` 方法会导致「全选」按钮无效；需手动添加 `setChecked(checked)` 转发到内部 `_checkbox`
