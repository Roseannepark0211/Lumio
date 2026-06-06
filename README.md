# Lumio

内容采集与素材管理桌面工具 — 通过分享链接下载 YouTube、Instagram、X (Twitter) 的图片/视频，自动入库管理。

![主界面](docs/images/素材库.png)

## 功能

- 粘贴链接自动识别平台（YouTube / Instagram / X）
- YouTube：选择清晰度，自动合并视频+音频；支持频道/播放列表批量下载
- Instagram：图片帖、视频帖、混合轮播帖、主页批量下载；最高画质下载
- X (Twitter)：视频下载
- 下载队列：暂停/继续/重试/恢复/全部操作；智能退避重试（5s→15s→30s）
- 错误分类：Cookie/网络/限流/内容/解析，显示友好提示
- 断点续传：YouTube/X 中断后自动续传
- 批量导入：粘贴多行 URL，一键全部加入队列
- 素材库：下载自动入库、缩略图预览、Collections 分类、收藏、多维搜索筛选
- 素材预览：图片缩放/平移/多图切换；视频/音频内置播放器
- 下载历史：搜索、平台筛选、打开文件/目录
- 下载统计：总下载数、体积、成功率、今日下载、各平台数量
- 文件冲突策略：重命名/跳过/覆盖/每次询问
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

Python 3.10+ / PySide6 / yt-dlp / instaloader / imageio-ffmpeg / requests / SQLAlchemy / Pillow

## 许可证

[MIT License](LICENSE) — 仅供个人学习使用。
