"""跨平台 User-Agent 生成（M5 修复）。

旧实现把 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..." 硬编码在 19 处，
macOS/Linux 运行时也伪装成 Windows UA，部分平台反爬可能识别异常。

新实现：
- DEFAULT_UA：运行时按 sys.platform 生成对应平台 UA
- chrome_ua(version)：动态生成指定 Chrome 版本的 UA
- WINDOWS_CHROME_UA：固定 Windows UA（仅用于已知必须 Windows UA 的场景，
  例如小红书 CDN 已验证跨平台 UA 会触发 502）

跨平台 token：
- Windows: "Windows NT 10.0; Win64; x64"
- macOS:   "Macintosh; Intel Mac OS X 10_15_7"
           （Chrome on Apple Silicon 仍报告 Intel，兼容性需要）
- Linux:   "X11; Linux x86_64"
"""

from __future__ import annotations

import sys


def _platform_token() -> str:
    """返回当前平台的 UA 平台 token。"""
    if sys.platform == "win32":
        return "Windows NT 10.0; Win64; x64"
    elif sys.platform == "darwin":
        # Chrome on Apple Silicon 仍报告 Intel Mac OS X（兼容性，Chrome 实际行为）
        return "Macintosh; Intel Mac OS X 10_15_7"
    else:
        return "X11; Linux x86_64"


def chrome_ua(version: int = 131) -> str:
    """生成跨平台 Chrome User-Agent。

    Args:
        version: Chrome 主版本号（如 131、120）
    """
    return (
        f"Mozilla/5.0 ({_platform_token()}) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version}.0.0.0 Safari/537.36"
    )


# ============================================================
# 常用 UA 常量（导入即用，运行时按平台生成）
# ============================================================

# 默认 UA（Chrome 131，跨平台）
DEFAULT_UA = chrome_ua(131)

# Chrome 120 UA（部分平台如 IG 移动 API 需要）
CHROME_120_UA = chrome_ua(120)

# 固定 Windows UA —— 仅用于已知必须 Windows UA 的场景：
# - 小红书 CDN（thumb_proxy.py 验证跨平台 UA 触发 502）
# - 微博 sinaimg.cn CDN（验证跨平台 UA 触发 403）
# 用前请加注释说明为何不能用 DEFAULT_UA
WINDOWS_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Windows Chrome 120（小红书 CDN 已验证）
WINDOWS_CHROME_120_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
