"""Lumio V4 — 抖音浏览器拦截提取（兜底方案）。

背景（2026-10-25 沙箱实测验证）：
- 抖音 Argus 升级后，无签名 aweme detail API 返回 403
  （"Blocked by ArgusSecurityPlugin Uifid Not Found"），
  share 页 HTML 也只剩 Argus 验证空壳，不再含视频数据。
- 但不逆向签名算法也能恢复：用 Playwright 真实浏览器打开
  分享页或 www 视频页，页面自己的 JS 会走完 Argus 验证，
  并给 aweme detail 请求签上 a_bogus + msToken；
  拦截该请求的 200 响应，直接取 aweme_detail 即可。
- 入口选择：视频默认 www 页优先，图文分享页优先。
  分享页只是带 Argus 预检的壳，启动过程受风控影响时好时坏
  （同一视频有时 Loading 卡死、零请求，有时正常触发签名详情），
  www 页跳过分享壳，更稳。

关键结论（实测）：
- 签名参数是页面 JS 运行时生成的，不存在"某个地方等你去找"；
  无头浏览器也能跑，但会话要先"养"：首次运行完成验证并落盘 cookie，
  之后复用同一 profile 即可直接带签名。因此 user_data_dir 默认落在
  应用目录下（~/.lumio/browser/douyin），不要每次用临时目录。
- 光把签名 URL 拷出来在 Python 侧重放不行（无浏览器 cookie 时返回
  200 空体），必须在浏览器内拦截响应。
- 作品本身不可看时，详情接口返回 200 但 aweme_detail 为 null，
  并带 filter_detail（"因作品权限或已被删除"），调用方应据此给出
  明确提示，而不是笼统的"解析失败"。

依赖：playwright 是可选依赖（pip install lumio[browser]），
未安装时本模块所有入口返回空结果并记日志，不抛异常。
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 详情接口 URL 特征（拦截用子串匹配，不依赖完整 URL）
_DETAIL_URL_MARK = "/aweme/v1/web/aweme/detail/"
# 分享页入口（打开后会 302 到 www.douyin.com/video/{id}，应用在该页内加载）
_SHARE_PAGE_URL = "https://www.iesdouyin.com/share/video/{}/"
# www 视频页入口（分享页卡住时的回退：实测同一视频分享页一直 Loading、
# 无任何 aweme 请求，而 www 页可正常触发签名详情）
_VIDEO_PAGE_URL = "https://www.douyin.com/video/{}/"

# 默认总等待时长（秒）：goto 可能超时但页面仍在后台加载，
# 实测从冷会话到拿到签名响应约需 60~120 秒
DEFAULT_TIMEOUT = 120


def playwright_available() -> bool:
    """Playwright 是否已安装（不触发浏览器启动）。"""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def find_system_browser() -> Optional[str]:
    """找本机已装的 Chrome/Edge 可执行文件，未找到返回 None。

    打包版没有 Playwright 自带浏览器时用它兜底：优先复用用户
    已装的浏览器，不用再下载一份 Chromium。
    """
    if sys.platform == "win32":
        candidates: list[str] = []
        for base in (
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base:
                continue
            # 显式反斜杠拼接（不用 os.path.join）：测试在 POSIX 上模拟
            # win32 时也能得到真实的 Windows 路径字符串
            candidates += [
                base + "\\Google\\Chrome\\Application\\chrome.exe",
                base + "\\Microsoft\\Edge\\Application\\msedge.exe",
            ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        for name in ("chrome", "msedge"):
            found = shutil.which(name)
            if found:
                return found
        return None
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
        home = os.environ.get("HOME", "")
        if home:
            candidates += [
                os.path.join(home, "Applications", "Google Chrome.app",
                             "Contents", "MacOS", "Google Chrome"),
                os.path.join(home, "Applications", "Microsoft Edge.app",
                             "Contents", "MacOS", "Microsoft Edge"),
            ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
    ):
        found = shutil.which(name)
        if found:
            return found
    return None


def browser_executable_available() -> bool:
    """任一浏览器可用：本机 Chrome/Edge，或 Playwright 自带浏览器。

    仅在解析失败后调用（探查会短暂启动 Playwright 驱动进程）。
    """
    if find_system_browser() is not None:
        return True
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def _default_user_data_dir() -> Path:
    from ..utils.config import _APP_DIR

    return _APP_DIR / "browser" / "douyin"


def extract_detail_from_payload(data: dict) -> tuple[Optional[dict], Optional[str]]:
    """从详情接口响应体中提取 aweme_detail 或不可看原因。

    Returns:
        (detail, filter_msg)：detail 非空表示拿到可用数据；
        filter_msg 非空表示作品本身不可看（如权限/已删除）；
        两者皆空表示该响应与目标视频无关或暂无结论。
    """
    if not isinstance(data, dict):
        return None, None
    detail = data.get("aweme_detail")
    if isinstance(detail, dict) and (detail.get("video") or detail.get("images")):
        return detail, None
    filter_detail = data.get("filter_detail")
    if isinstance(filter_detail, dict):
        msg = filter_detail.get("detail_msg") or ""
        if msg:
            return None, msg
    return None, None


def fetch_aweme_detail_via_browser(
    video_id: str,
    timeout: int = DEFAULT_TIMEOUT,
    user_data_dir: Optional[Path] = None,
    executable_path: Optional[str] = None,
    chromium_args: Optional[list[str]] = None,
    is_note: bool = False,
) -> tuple[Optional[dict], Optional[str]]:
    """用真实浏览器拦截 aweme detail 响应，返回 (detail, filter_msg)。

    Args:
        video_id: 抖音 aweme_id。
        timeout: 总等待时长（秒），超时返回 (None, None)。
        user_data_dir: 浏览器 profile 目录，默认 ~/.lumio/browser/douyin；
            复用同一目录是"养会话"的关键，不要传临时目录。
        executable_path: 指定 Chromium 可执行文件（测试用；默认按
            Playwright 自带浏览器 → 本机 Chrome/Edge 的顺序自动解析，
            两者皆无时由 Playwright 报错并返回 (None, None)）。
        chromium_args: 透传给 Chromium 的启动参数（如沙箱内需
            --no-sandbox；用户机器上一般不需要）。
        is_note: 是否为图文帖。图文走分享页优先（已验证），视频走
            www 页优先：分享页只是带 Argus 预检的壳，启动过程受风控
            影响时好时坏（同一视频有时 Loading 卡死、零请求，有时
            正常触发签名详情），而 www 页跳过分享壳，更稳。

    Returns:
        (detail, filter_msg)，见 extract_detail_from_payload。
        Playwright 未安装时返回 (None, None) 并记 warning。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "抖音浏览器兜底不可用：未安装 Playwright，"
            "请执行 pip install lumio[browser] 后重试"
        )
        return None, None

    profile_dir = Path(user_data_dir) if user_data_dir else _default_user_data_dir()
    captured: dict[str, object] = {}

    def _on_response(resp) -> None:
        if _DETAIL_URL_MARK not in resp.url:
            return
        if resp.status != 200:
            return
        try:
            data = resp.json()
        except Exception:
            return
        detail, filter_msg = extract_detail_from_payload(data)
        if detail is not None:
            captured["detail"] = detail
        elif filter_msg:
            captured.setdefault("filter_msg", filter_msg)

    try:
        with sync_playwright() as p:
            launch_kwargs: dict = {"headless": True}
            # 浏览器解析：显式指定 > Playwright 自带（版本最匹配）>
            # 本机 Chrome/Edge（打包版无自带浏览器时的主力）>
            # 都没有则不传 executable_path，让 Playwright 报明确错误。
            exe = executable_path
            if not exe:
                try:
                    managed = Path(p.chromium.executable_path)
                except Exception:
                    managed = None
                if managed is not None and managed.exists():
                    exe = None  # 自带浏览器存在，沿用 Playwright 默认
                else:
                    exe = find_system_browser()
            if exe:
                launch_kwargs["executable_path"] = exe
            if chromium_args:
                launch_kwargs["args"] = chromium_args
            context = p.chromium.launch_persistent_context(
                str(profile_dir), **launch_kwargs
            )
            try:
                # 隐藏 webdriver 标记（不改 UA：实测改 UA 反而导致验证不通过）
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', "
                    "{ get: () => undefined })"
                )
                page = context.new_page()
                page.on("response", _on_response)
                # 入口页：图文走分享页优先（已验证），视频走 www 页优先。
                # 分享页只是带 Argus 预检的壳，启动过程受风控影响时好时坏
                # （同一视频有时 Loading 卡死、零请求，有时正常触发签名详情），
                # 而 www 页跳过分享壳，更稳。
                # goto 用 commit 即返回，不等 DOM：应用在后台继续加载，
                # 轮询期间仍能捕获签名请求（冷会话下 domcontentloaded
                # 常常 60s 超时，反而浪费预算）。
                share_url = _SHARE_PAGE_URL.format(video_id)
                www_url = _VIDEO_PAGE_URL.format(video_id)
                entry_urls = (
                    [share_url, www_url] if is_note else [www_url, share_url]
                )
                per_page = max(30.0, timeout / len(entry_urls))
                deadline = time.monotonic() + timeout
                for page_url in entry_urls:
                    if time.monotonic() >= deadline:
                        break
                    if "detail" in captured or "filter_msg" in captured:
                        break
                    page_deadline = min(deadline, time.monotonic() + per_page)
                    try:
                        page.goto(page_url, wait_until="commit", timeout=30_000)
                    except Exception as e:
                        logger.debug(
                            "抖音入口页跳转未完成 %s，继续等待捕获：%s", page_url, e
                        )
                    while time.monotonic() < page_deadline:
                        if "detail" in captured or "filter_msg" in captured:
                            break
                        page.wait_for_timeout(1000)
            finally:
                context.close()
    except Exception as e:
        logger.warning("抖音浏览器拦截失败（video_id=%s）：%s", video_id, e)
        return None, None

    if "detail" in captured:
        logger.info("抖音浏览器拦截成功（video_id=%s）：拿到 aweme_detail", video_id)
        return captured["detail"], None
    if "filter_msg" in captured:
        logger.info("抖音作品不可看（video_id=%s）：%s", video_id, captured["filter_msg"])
        return None, str(captured["filter_msg"])
    logger.warning("抖音浏览器拦截超时（video_id=%s）：未捕获到详情响应", video_id)
    return None, None
