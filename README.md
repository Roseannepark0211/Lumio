# Lumio

Instagram & YouTube 视频/图片下载桌面工具（PySide6 GUI）。

## 安装

```powershell
pip install -e .
python -m getvp.main
```

## 功能

- 粘贴 YouTube / Instagram 链接，自动识别平台并下载
- YouTube：选择清晰度，自动合并视频+音频（内置 ffmpeg）
- Instagram：支持图片帖、视频帖、混合轮播帖；需导入浏览器 Cookie
- 自定义文件名，默认作者名+时间戳
- 中/英双语界面

## 依赖

Python 3.10+ / PySide6 / yt-dlp / instaloader / imageio-ffmpeg / requests
