# Lumio

内容采集与素材管理桌面工具 — 通过分享链接下载 YouTube、Instagram、X (Twitter) 及国内主流平台（B站/抖音/快手/微博/小红书）的图片/视频，自动入库管理。

![主界面](docs/images/素材库.png)

## 功能

- 粘贴链接自动识别平台（YouTube / Instagram / X / B站 / 抖音 / 快手 / 微博 / 小红书）
- YouTube：选择清晰度，自动合并视频+音频；支持频道/播放列表批量下载
- Instagram：图片帖、视频帖、混合轮播帖、主页批量下载；最高画质下载
- X (Twitter)：视频下载、图片下载（需 auth cookie）、用户主页批量下载
- X-Sou 搜索：Home 页面搜索按钮，调 X-Sou API 搜索推文；结果列表含缩略图+预览+分页+勾选入队
- B站：BV/av 号视频下载，b23.tv 短链自动展开
- 抖音：视频下载（多清晰度，自动 ttwid 访客标识，无需 cookie）、图文帖（note）下载、a_bogus 签名服务可选增强（拿 H.265 档位）
- 快手：短视频解析下载
- 微博：图片/视频/多图/转发/livephoto 下载；sinaimg.cn CDN 需要 Cookie + Referer
- 小红书：图片/视频笔记下载，xhslink.com/xhslink.cn 短链自动展开
- Inbox 收件箱：接收浏览器扩展采集的 URL，等待用户下载；支持格式选择（单个）/最高画质（批量）
- 通知系统：环境/依赖/版本通知 + 分类筛选 + 永久通知（如 IG 风险提示）
- 系统托盘：关闭窗口最小化到托盘，保持后台运行
- 本地 API 服务：Flask 接收浏览器扩展采集内容（127.0.0.1:38900）
- Telegram Bot 服务：轮询 Bot API，接收用户发送的链接/媒体，自动写入 Inbox
- Apify IG 代理：通过 Apify Actor 代理提取 Instagram 数据，避免账号风控
- 国内平台支持：V4 Provider 架构统一支持；短链自动展开（t.cn/b23.tv/xhslink.com/iesdouyin.com/v.douyin.com）；URL → MediaInfo 两级缓存（内存+文件）
- 下载队列：暂停/继续/重试/恢复/全部操作；智能退避重试（5s→15s→30s）
- 错误分类：Cookie/网络/限流/内容/解析，显示友好提示
- 断点续传：YouTube/X 中断后自动续传
- 批量导入：粘贴多行 URL，一键全部加入队列
- 素材库：下载自动入库、缩略图预览、Collections 分类（右键重命名/删除）、收藏、多维搜索筛选（文本+平台+类型+收藏+日期范围+批次）、批量操作（全选/批量收藏/批量删除/批量加入 Collection）
- 素材预览：图片缩放/平移/多图切换；视频/音频内置播放器
- 下载历史：搜索、平台筛选、打开文件/目录、批量批次分组折叠
- 下载统计：总下载数、体积、成功率、今日下载、各平台数量
- 文件冲突策略：重命名/跳过/覆盖/每次询问
- 凭证管理：设置页 Cookie/API 凭证分组可折叠（QToolButton），避免凭证过多布局混乱
- Home 预览：清晰度选择列独立放置于文件名与格式之间；多素材预览卡片点击选中、按钮入队
- Light / Dark 主题切换
- 中/英双语界面

## 安装

### 方式一：下载 .exe（推荐，无需 Python 环境）

从 [Releases](../../releases) 页面下载对应系统的安装包，解压后直接运行。

### 方式二：pip 安装

```powershell
# 需要 Python 3.10+
pip install .
lumio
```

### 方式三：开发者模式

```powershell
pip install -e .
python -m lumio.main
```

## 运行测试

```powershell
pip install -e ".[test]"
PYTHONPATH=src python -m pytest tests/ -v
```

## 截图

| 使用界面 | 预览功能 | 设置界面 |
|---------|---------|---------|
| ![使用界面](docs/images/使用界面.png) | ![预览功能](docs/images/预览功能.png) | ![设置界面](docs/images/设置界面.png) |

## 技术栈

Python 3.10+ / PySide6 / yt-dlp / instaloader / imageio-ffmpeg / requests / SQLAlchemy / Pillow / Flask / python-telegram-bot / apify-client / V4 Provider 系统

## 许可证

[MIT License](LICENSE) — 仅供个人学习使用。
