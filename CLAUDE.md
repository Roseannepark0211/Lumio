# Lumio

个人自用桌面工具，通过分享链接下载 Instagram 和 YouTube 的图片/视频。

## 技术栈

- Python 3.10+ / PySide6 (Qt) 桌面 GUI
- yt-dlp — YouTube 下载（含 ffmpeg 合并视频+音频）
- instaloader — Instagram 下载（图片+视频+轮播帖）
- imageio-ffmpeg — 内置 ffmpeg 二进制，无需系统安装
- 中/英双语（i18n），设置对话框切换

## 快速开始

```powershell
pip install -e .
python -m getvp.main
```

## 项目结构

```
src/getvp/
  main.py           — 入口
  downloader.py      — 下载引擎（yt-dlp + instaloader 封装）
  queue_manager.py   — 下载队列管理（单任务/批量/暂停/重试）
  i18n.py            — 中/英翻译字典
  assets/
    logo.png         — 应用图标（窗口 + 任务栏）
  gui/
    window.py        — 主窗口（URL输入→预览→格式选择→下载队列）
    queue_panel.py   — 队列面板（任务卡片 + 全局操作按钮）
    settings.py      — 设置对话框（Cookie导入 + 语言切换）
    styles.py        — 深色主题样式表
  utils/
    url_parser.py    — URL 平台识别（YouTube / Instagram / 不支持）
    config.py        — 配置读写（~/.getvp/config.json）
tests/
  test_url_parser.py — URL 解析单测（11 cases）
```

## 运行验证

```powershell
PYTHONPATH=src python -m pytest tests/ -v   # 单测
python -m getvp.main                          # 启动 GUI
```

## 关键行为

- **平台自动识别**：粘贴链接即识别 YouTube/Instagram，无需手动选
- **文件名**：默认用作者名+发布时间戳；可手动修改；轮播帖自动编号
- **YouTube 格式选择**：纯视频自动合并音频，纯音频自动合并视频
- **Instagram Cookie**：设置对话框导入 Netscape 格式 cookie 文件
- **语言切换**：设置对话框选择中/英，确认后立即重启生效
- **ffmpeg**：通过 imageio-ffmpeg 内置，二进制名 `ffmpeg-win-x86_64-v7.1.exe`
- **队列行为**：单任务"开始"只启动该任务；"全部开始"按 max_workers 并发上限调度；任务完成后不自动启动下一个

## 踩坑记录

- yt-dlp 的 `ffmpeg_location` 必须指向**完整二进制路径**，不能只给目录（二进制名非标准）
- PySide6 跨线程操作 GUI 控件会崩溃，必须用 Signal/Slot 机制
- Instagram 轮播帖中 yt-dlp 不支持图片，需用 instaloader 处理
- 代理环境下 Instagram 请求偶发 SSL 错误，instaloader 内建重试机制可自愈
