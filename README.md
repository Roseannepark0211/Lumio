# Lumio

内容采集与素材管理桌面工具 — 通过分享链接下载 YouTube、Instagram、X (Twitter) 的图片/视频，自动入库管理。

## 安装

```powershell
pip install -e .
python -m getvp.main
```

## 功能

- 粘贴链接自动识别平台（YouTube / Instagram / X）
- YouTube：选择清晰度，自动合并视频+音频；支持频道/播放列表批量下载
- Instagram：图片帖、视频帖、混合轮播帖、主页批量下载；最高画质下载
- X (Twitter)：视频下载
- 下载队列：暂停/继续/重试/全部操作
- 素材库：下载自动入库、缩略图预览、Collections 分类、收藏/置顶、多维搜索筛选
- 下载历史：搜索、平台筛选、打开文件/目录
- 下载统计：总下载数、体积、各平台数量
- Light / Dark 主题切换
- 中/英双语界面

## 技术栈

Python 3.10+ / PySide6 / yt-dlp / instaloader / imageio-ffmpeg / requests / SQLAlchemy / Pillow
