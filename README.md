# Lumio

内容采集与素材管理桌面工具 — 通过分享链接下载 YouTube、Instagram、X (Twitter) 及国内主流平台（B站/抖音/快手/微博/小红书）的图片/视频，自动入库管理。

![主页](docs/images/主页.png)

## 架构

Lumio 采用 **Electron + React 前端 / Python FastAPI 后端** 双进程架构：

```
┌─────────────────────────────┐     HTTP/WS      ┌──────────────────────────┐
│  Electron + React 前端       │  ←───────────→   │  Python FastAPI 后端     │
│  (frontend/)                │                  │  (src/lumio/api_fastapi) │
│  - Vite + TypeScript        │                  │  - 包装现有 manager      │
│  - Tailwind CSS             │                  │  - WebSocket 推送进度    │
│  - Liquid Glass 设计稿      │                  │  - yt-dlp / instaloader  │
└─────────────────────────────┘                  └──────────────────────────┘
                                                         ↓
                                                  现有 Python 业务
                                                  Provider 系统 / SQLAlchemy /
                                                  Flask / Telegram Bot
```

启动时 Electron 主进程 spawn FastAPI 子进程（随机端口 + token），通过 HTTP/WS 通信；退出时优雅关闭后端，避免端口残留。

## 功能

### 平台支持

- **YouTube**：选择清晰度，自动合并视频+音频；支持频道/播放列表批量下载
- **Instagram**：图片帖、视频帖、混合轮播帖、主页批量下载；最高画质下载（cookie 模式调移动 API，复现 saveinta.com 机制）
- **X (Twitter)**：视频下载、图片下载（需 `auth_token` + `ct0` cookie）、用户主页批量下载
- **X-Sou 搜索**：Home 页面搜索按钮（设置页可开关，默认关闭含 18+ 警告），调 X-Sou API 搜索推文；结果列表含缩略图+预览+分页+勾选入队；`@username` 自动转 `from:username`
- **B站**：BV/av 号视频下载，b23.tv 短链自动展开；DASH 多清晰度（最高 8K，按账号权限降级）
- **抖音**：视频下载（多清晰度，自动 ttwid 访客标识，无需 cookie）、图文帖（note）下载、a_bogus 签名服务可选增强（拿 H.265 档位）
- **快手**：短视频解析下载
- **微博**：图片/视频/多图/转发/livephoto 下载；sinaimg.cn CDN 需要 Cookie + Referer
- **小红书**：图片/视频笔记下载，xhslink.com/xhslink.cn 短链自动展开

### 下载与队列

- 下载队列：暂停/继续/重试/恢复/全部操作；智能退避重试（5s→15s→30s）
- 断点续传：YouTube/X 中断后自动续传；直链下载支持 Range header + append 模式
- 错误分类：Cookie/网络/限流/内容/解析，显示友好提示
- 批量导入：粘贴多行 URL，一键全部加入队列
- 批量下载：IG/YouTube/X 主页或频道链接，弹出批量对话框
- 文件冲突策略：重命名/跳过/覆盖/每次询问
- 多流下载进度：yt-dlp 视频+音频合并时正确累计进度，避免 100% 后归 0

### 素材管理

- **素材库**：下载自动入库、缩略图预览、Collections 分类（右键重命名/删除）、收藏、多维搜索筛选（文本+平台+类型+收藏+日期范围+批次）、批量操作（全选/批量收藏/批量删除/批量加入 Collection）；卡片右下角按钮智能切换 —— 全部视图下显示「📁+」弹出添加菜单，分类视图下显示「✕」直接从当前分类移除
- **素材预览**：图片缩放/平移/多图切换；视频/音频内置播放器
- **下载历史**：搜索、平台筛选、打开文件/目录、批量批次分组折叠
- **下载统计**：总下载数、体积、成功率、今日下载、各平台数量

### 系统集成

- **Inbox 收件箱**：接收浏览器扩展采集的 URL，等待用户下载；支持格式选择（单个）/最高画质（批量）
- **通知系统**：环境/依赖/版本通知 + 分类筛选 + 永久通知（IG 风险提示、VPN/代理、媒体播放器推荐、Telegram Bot、Apify Token）
- **系统托盘**：Liquid Glass 风格自定义菜单弹窗，关闭窗口最小化到托盘保持后台运行
- **本地 API 服务**：Flask 接收浏览器扩展采集内容（127.0.0.1:38900）
- **Telegram Bot 服务**：轮询 Bot API，接收用户发送的链接/媒体，自动写入 Inbox；支持本地 Bot API Server 突破 20MB 限制
- **Apify IG 代理**：通过 Apify Actor 代理提取 Instagram 数据，避免账号风控
- **缓存管理**：统一管理 4 个缓存目录（inbox_media/thumbs/provider_cache/preview），支持手动/定时清理
- **凭证管理**：设置页 Cookie/API 凭证分组可折叠，避免凭证过多布局混乱

### 界面

- V4 Provider 架构统一支持所有平台；短链自动展开；URL → MediaInfo 两级缓存
- Home 预览：清晰度选择列独立放置于文件名与格式之间；多素材预览卡片点击选中、按钮入队；预览区比例自适应（横屏/正方形/竖屏）
- Sidebar 红点徽章（1-9 圆点 / 10-99 胶囊 / ≥100 显示 99+）
- Light / Dark 主题切换
- 中/英双语界面
- Liquid Glass 设计风格（毛玻璃 + 柔和色彩 + 大圆角，克制而非装饰堆砌）

## 安装

### 方式一：下载安装包（推荐，无需任何开发环境）

从 [Releases](../../releases) 页面下载对应系统的安装包（Windows NSIS / macOS DMG / Linux AppImage），双击安装即可。

安装包内已包含 Electron 前端 + PyInstaller 打包的 Python 后端，无需额外配置 Python / Node.js 环境。

### 方式二：开发者模式运行（前端 + 后端分离）

适用于开发调试，可独立修改前端或后端代码。

**前置要求**：Python 3.10+ / Node.js 18+ / npm

```powershell
# 1. 安装 Python 后端依赖
pip install -e .

# 2. 安装前端依赖
cd frontend
npm install

# 3. 启动开发模式（同时拉起 Vite + Electron + FastAPI 子进程）
npm run dev:electron
```

`dev:electron` 会自动：
- 编译 Electron 主进程 TypeScript（`electron/` → `dist-electron/`）
- 启动 Vite Dev Server（http://localhost:5173）
- 启动 Electron 主进程，主进程 spawn FastAPI 子进程（随机端口 + token）
- Electron 窗口加载 `VITE_DEV_SERVER_URL`，热重载生效

### 方式三：仅运行 Python 后端（API 模式）

适用于不需要前端 UI、只想调用 API 的场景：

```powershell
pip install -e .
lumio-api              # 启动 FastAPI 服务（默认 127.0.0.1:8000）
```

## 打包构建

构建完整安装包（PyInstaller + electron-builder）：

```powershell
# 前置：先 pip install -e . 和 cd frontend && npm install
cd frontend
npm run build:all      # = build:backend + build + build:electron + electron-builder
```

输出在 `frontend/release/` 目录下。

- `build:backend` — PyInstaller 把 `src/lumio/` 打包成 `LumioAPI.exe`（含 Python runtime）复制到 `frontend/python-backend/`
- `build` — TypeScript 编译 + Vite 构建前端到 `dist/`
- `build:electron` — 编译 `electron/` TypeScript 到 `dist-electron/`
- `electron-builder` — 把 `dist/` + `dist-electron/` + `python-backend/` 打包成系统安装包

## 运行测试

```powershell
pip install -e ".[test]"
PYTHONPATH=src python -m pytest tests/ -v --ignore=tests/test_integration.py
```

## 截图

| 主页 | 素材库 |
|------|--------|
| ![主页](docs/images/主页.png) | ![素材库](docs/images/素材库.png) |

## 浏览器扩展

Chrome/Edge 共用（Manifest V3）：

- 右键菜单发送页面/链接/视频/图片到 Lumio
- content.js 提取 YouTube/X 页面元数据
- IG 一次性注入 `ig_extract.js` 从 DOM 读取媒体直链（不调 IG API，避免账号风险）

详见 [extension/](extension/) 目录。

## 技术栈

**前端**：Electron 31 / React 18 / TypeScript / Vite / Tailwind CSS / Zustand / react-window（虚拟列表）

**后端**：Python 3.10+ / FastAPI / yt-dlp / instaloader / imageio-ffmpeg / requests / SQLAlchemy / Pillow / Flask / python-telegram-bot / apify-client / V4 Provider 系统

## 许可证

[MIT License](LICENSE) — 仅供个人学习使用。
