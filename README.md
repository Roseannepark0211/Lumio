# Lumio

内容采集与素材管理桌面工具 — 通过分享链接下载 YouTube、Instagram、X (Twitter) 及国内主流平台（B站/抖音/快手/微博/小红书）的图片/视频，自动入库管理。

![主页](docs/images/主页.png)

## 架构

Lumio 采用 **Electron + React 前端 / Python FastAPI 后端** 双进程架构。

- 前端：Electron + React + TypeScript + Vite + Tailwind CSS，负责 UI 渲染与用户交互
- 后端：Python + FastAPI，包装 yt-dlp / instaloader / Provider 系统等业务能力
- 通信：HTTP（REST API） + WebSocket（实时进度推送）
- 启动时 Electron 主进程 spawn FastAPI 子进程（随机端口 + token），退出时优雅关闭后端

## 功能

### 平台支持

- **YouTube**：清晰度选择，自动合并视频+音频；频道/播放列表批量下载
- **Instagram**：图片/视频/轮播帖、主页批量下载；cookie 模式调移动 API 取最高画质
- **X (Twitter)**：视频/图片下载、用户主页批量下载（需 `auth_token` + `ct0` cookie）
- **X-Sou 搜索**：调 X-Sou API 搜索推文，结果含缩略图+预览+分页+勾选入队
- **B站**：BV/av 号视频下载，b23.tv 短链自动展开，DASH 多清晰度
- **抖音**：视频下载（多清晰度，自动 ttwid 访客标识）、图文帖下载
- **快手**：短视频解析下载
- **微博**：图片/视频/多图/转发/livephoto 下载
- **小红书**：图片/视频笔记下载，xhslink.com/xhslink.cn 短链自动展开

### 下载与队列

- 暂停/继续/重试/恢复/全部操作；智能退避重试（5s→15s→30s）
- YouTube/X 断点续传；直链下载支持 Range header + append 模式
- 错误自动分类：Cookie/网络/限流/内容/解析
- 文件冲突策略：重命名/跳过/覆盖/每次询问

### 素材管理

- **素材库**：下载自动入库、缩略图预览、Collections 分类（右键重命名/删除）、收藏、多维搜索筛选、批量操作
- **素材预览**：图片缩放/平移/多图切换；视频/音频内置播放器
- **下载历史**：搜索、平台筛选、批次分组折叠
- **下载统计**：总下载数、体积、成功率、今日下载、各平台数量

### 系统集成

- **Inbox 收件箱**：接收浏览器扩展采集的 URL
- **通知系统**：环境/依赖/版本通知 + 分类筛选 + 永久通知
- **系统托盘**：Liquid Glass 风格自定义菜单，关闭窗口最小化到托盘
- **本地 API 服务**：Flask 接收浏览器扩展采集内容
- **Telegram Bot 服务**：接收用户发送的链接/媒体，自动写入 Inbox
- **Apify IG 代理**：通过 Apify Actor 代理提取 Instagram 数据，避免账号风控
- **缓存管理**：统一管理 4 个缓存目录，支持手动/定时清理

### 界面

- V4 Provider 架构统一支持所有平台；短链自动展开
- Light / Dark 主题切换；中/英双语界面
- Liquid Glass 设计风格（毛玻璃 + 柔和色彩 + 大圆角）

## 安装

### 方式一：下载安装包（推荐）

从 [Releases](../../releases) 页面下载对应系统的安装包（Windows NSIS / macOS DMG / Linux AppImage），双击安装即可。安装包内已包含 Electron 前端 + PyInstaller 打包的 Python 后端，无需额外环境。

### 方式二：开发者模式

**前置要求**：Python 3.10+ / Node.js 18+ / npm

```powershell
# 1. 安装 Python 后端依赖
pip install -e .

# 2. 安装前端依赖并启动开发模式
cd frontend
npm install
npm run dev:electron
```

`dev:electron` 会同时拉起 Vite Dev Server、Electron 主进程和 FastAPI 子进程，支持前端热重载。

### 方式三：仅运行 Python 后端

```powershell
pip install -e .
lumio-api              # 启动 FastAPI 服务
```

## 截图

| 主页 | 素材库 |
|------|--------|
| ![主页](docs/images/主页.png) | ![素材库](docs/images/素材库.png) |

## 浏览器扩展

Chrome/Edge 共用（Manifest V3）：

- 右键菜单发送页面/链接/视频/图片到 Lumio
- content.js 提取 YouTube/X 页面元数据
- IG 一次性注入 `ig_extract.js` 从 DOM 读取媒体直链（不调 IG API）

详见 [extension-v2/](extension-v2/) 目录。

## 技术栈

- **前端**：Electron / React / TypeScript / Vite / Tailwind CSS / Zustand / react-window
- **后端**：Python / FastAPI / yt-dlp / instaloader / SQLAlchemy / Pillow / Flask / python-telegram-bot / apify-client

## 许可证

[MIT License](LICENSE) — 仅供个人学习使用。
