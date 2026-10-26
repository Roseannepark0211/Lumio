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
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 详情接口 URL 特征（拦截用子串匹配，不依赖完整 URL）
_DETAIL_URL_MARK = "/aweme/v1/web/aweme/detail/"
# 主页作品列表接口 URL 特征（拦截用子串匹配）
_POST_LIST_URL_MARK = "/aweme/v1/web/aweme/post/"
# 主页入口（sec_uid 形式，如 MS4wLjABAAAA...）
_USER_PAGE_URL = "https://www.douyin.com/user/{}/"
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


# === 常驻暖浏览器上下文（解析提速） ===
# Playwright 同步 API 对象绑定到创建它的线程；FastAPI 经 to_thread 在
# 线程池里调用解析，跨线程复用同一上下文会报错，且同一 profile 目录
# 同时开两个持久上下文会撞锁。因此常驻上下文实行“单线程独占”：
# 同线程 + 同 profile + 同启动参数才复用，否则关掉旧的、当前线程重建；
# 任何一步失败都回落到冷启动（现起现关），不影响正确性。
# 注意：暖来自一次成功解析养出的会话，不是光启动浏览器——首个解析
# 仍是冷耗时，成功解析后后续解析复用会话（验证结论）。
_warm_lock = threading.Lock()
_warm_playwright = None
_warm_context = None
_warm_owner_thread = None
_warm_fingerprint = None
_warm_atexit_registered = False


def _add_stealth_init_script(context) -> None:
    """隐藏 webdriver 标记（不改 UA：实测改 UA 反而导致验证不通过）。"""
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', "
        "{ get: () => undefined })"
    )


def _resolve_chromium_executable(pw, executable_path):
    """浏览器解析：显式指定 > Playwright 自带（版本最匹配）>
    本机 Chrome/Edge（打包版无自带浏览器时的主力）>
    都没有则返回 None，让 Playwright 报明确错误。"""
    if executable_path:
        return executable_path
    try:
        managed = Path(pw.chromium.executable_path)
    except Exception:
        managed = None
    if managed is not None and managed.exists():
        return None  # 自带浏览器存在，沿用 Playwright 默认
    return find_system_browser()


def _drop_warm_context_locked() -> None:
    """关掉常驻上下文并停掉 Playwright（调用方须持 _warm_lock）。"""
    global _warm_playwright, _warm_context, _warm_owner_thread, _warm_fingerprint
    ctx, pw = _warm_context, _warm_playwright
    _warm_context = None
    _warm_playwright = None
    _warm_owner_thread = None
    _warm_fingerprint = None
    if ctx is not None:
        try:
            ctx.close()
        except Exception:
            pass
    if pw is not None:
        try:
            pw.stop()
        except Exception:
            pass


def close_warm_context() -> None:
    """公开关闭入口（应用退出、测试清理用）。"""
    with _warm_lock:
        _drop_warm_context_locked()


def _acquire_warm_context(user_data_dir, executable_path, chromium_args,
                          playwright_factory=None):
    """获取常驻上下文；建不起来返回 None（调用方走冷启动）。

    playwright_factory 默认 sync_playwright，测试可注入 fake。
    """
    global _warm_playwright, _warm_context, _warm_owner_thread
    global _warm_fingerprint, _warm_atexit_registered
    if playwright_factory is None:
        try:
            from playwright.sync_api import sync_playwright as playwright_factory
        except ImportError:
            return None
    profile_dir = Path(user_data_dir) if user_data_dir else _default_user_data_dir()
    fingerprint = (str(profile_dir), executable_path, tuple(chromium_args or []))
    with _warm_lock:
        if (_warm_context is not None
                and _warm_owner_thread == threading.get_ident()
                and _warm_fingerprint == fingerprint):
            return _warm_context
        # 线程、profile 或启动参数变了：关旧建新，避免跨线程使用与 profile 锁冲突
        _drop_warm_context_locked()
        try:
            pw = playwright_factory().start()
            exe = _resolve_chromium_executable(pw, executable_path)
            launch_kwargs: dict = {"headless": True}
            if exe:
                launch_kwargs["executable_path"] = exe
            if chromium_args:
                launch_kwargs["args"] = chromium_args
            ctx = pw.chromium.launch_persistent_context(str(profile_dir), **launch_kwargs)
            _add_stealth_init_script(ctx)
        except Exception:
            _drop_warm_context_locked()
            return None
        _warm_playwright = pw
        _warm_context = ctx
        _warm_owner_thread = threading.get_ident()
        _warm_fingerprint = fingerprint
        if not _warm_atexit_registered:
            import atexit
            atexit.register(close_warm_context)
            _warm_atexit_registered = True
        return ctx


def _capture_detail(context, video_id, is_note, deadline):
    """在给定上下文里开新页、拦截详情响应，返回 (detail, filter_msg)。

    页由本函数开关（常驻上下文不关闭，冷路径随后有关上下文）。
    deadline 为绝对时间（monotonic），到时未捕获即返回 (None, None)。
    """
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

    page = context.new_page()
    try:
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
        remaining = max(0.0, deadline - time.monotonic())
        per_page = max(30.0, remaining / len(entry_urls))
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
        try:
            page.close()
        except Exception:
            pass
    if "detail" in captured:
        logger.info("抖音浏览器拦截成功（video_id=%s）：拿到 aweme_detail", video_id)
        return captured["detail"], None
    if "filter_msg" in captured:
        logger.info("抖音作品不可看（video_id=%s）：%s", video_id, captured["filter_msg"])
        return None, str(captured["filter_msg"])
    logger.warning("抖音浏览器拦截超时（video_id=%s）：未捕获到详情响应", video_id)
    return None, None


def _fetch_cold(video_id, is_note, deadline, user_data_dir,
                executable_path, chromium_args):
    """冷启动：现起现关（原 fetch 逻辑）。deadline 为绝对时间。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "抖音浏览器兜底不可用：未安装 Playwright，"
            "请执行 pip install lumio[browser] 后重试"
        )
        return None, None

    profile_dir = Path(user_data_dir) if user_data_dir else _default_user_data_dir()
    try:
        with sync_playwright() as p:
            launch_kwargs: dict = {"headless": True}
            exe = _resolve_chromium_executable(p, executable_path)
            if exe:
                launch_kwargs["executable_path"] = exe
            if chromium_args:
                launch_kwargs["args"] = chromium_args
            context = p.chromium.launch_persistent_context(
                str(profile_dir), **launch_kwargs
            )
            try:
                _add_stealth_init_script(context)
                return _capture_detail(context, video_id, is_note, deadline)
            finally:
                context.close()
    except Exception as e:
        logger.warning("抖音浏览器拦截失败（video_id=%s）：%s", video_id, e)
        return None, None


def fetch_aweme_detail_via_browser(
    video_id: str,
    timeout: int = DEFAULT_TIMEOUT,
    user_data_dir: Optional[Path] = None,
    executable_path: Optional[str] = None,
    chromium_args: Optional[list[str]] = None,
    is_note: bool = False,
    use_warm: bool = False,
    _playwright_factory=None,
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
        use_warm: 复用常驻上下文（解析提速）。首个解析仍是冷耗时，
            成功解析后后续解析复用会话；常驻建不起来或中途失效时
            在剩余预算内回落冷启动。默认 False（调用方显式开启，
            避免改变其他调用方的行为）。
        _playwright_factory: 测试注入用（默认 sync_playwright）。

    Returns:
        (detail, filter_msg)，见 extract_detail_from_payload。
        Playwright 未安装时返回 (None, None) 并记 warning。
    """
    deadline = time.monotonic() + timeout
    if use_warm:
        ctx = None
        try:
            ctx = _acquire_warm_context(
                user_data_dir, executable_path, chromium_args,
                _playwright_factory)
        except Exception:
            ctx = None
        if ctx is not None:
            try:
                return _capture_detail(ctx, video_id, is_note, deadline)
            except Exception as e:
                logger.debug("常驻上下文捕获失败，回落冷启动：%s", e)
                with _warm_lock:
                    _drop_warm_context_locked()
        if time.monotonic() < deadline:
            return _fetch_cold(
                video_id, is_note, deadline,
                user_data_dir, executable_path, chromium_args)
        return None, None
    return _fetch_cold(
        video_id, is_note, deadline,
        user_data_dir, executable_path, chromium_args)


def parse_user_post_aweme(aweme: dict) -> Optional[dict]:
    """把主页列表接口的一项 aweme 解析为作品 dict。

    返回键：url, title, thumbnail, media_type（"video"/"image"），
    duration（视频秒数，图文为 None），image_count（图文图数，
    视频为 0），post_time（YYYYMMDD_HHMMSS），aweme_id, author,
    author_id。解析不出 aweme_id 时返回 None（调用方跳过该项）。

    注意：aweme 结构与 aweme_detail 里的单条结构一致（desc /
    author / video / images / create_time），因此字段取法与
    douyin.py 的 _parse_aweme_detail 对齐。
    """
    if not isinstance(aweme, dict):
        return None
    aweme_id = str(aweme.get("aweme_id", "") or "")
    if not aweme_id:
        return None
    title = aweme.get("desc", "") or ""
    author_info = aweme.get("author", {}) or {}
    author = author_info.get("nickname", "") or ""
    author_id = str(author_info.get("uid", "") or "")

    post_time = ""
    create_time = aweme.get("create_time", 0)
    if create_time:
        import datetime

        try:
            ts = int(create_time)
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            post_time = dt.strftime("%Y%m%d_%H%M%S")
        except (ValueError, OSError):
            post_time = str(create_time)

    images_list = aweme.get("images") or []
    if images_list:
        first = images_list[0] or {}
        url_list = first.get("url_list", []) or []
        thumbnail = url_list[0] if url_list else ""
        return {
            "url": f"https://www.douyin.com/note/{aweme_id}/",
            "title": title,
            "thumbnail": thumbnail,
            "media_type": "image",
            "duration": None,
            "image_count": len(images_list),
            "post_time": post_time,
            "aweme_id": aweme_id,
            "author": author,
            "author_id": author_id,
        }

    video_info = aweme.get("video", {}) or {}
    cover = video_info.get("origin_cover", {}) or video_info.get("cover", {})
    cover_urls = cover.get("url_list", []) or []
    thumbnail = cover_urls[0] if cover_urls else ""
    raw_duration = aweme.get("duration", 0) or video_info.get("duration", 0) or 0
    duration = None
    if raw_duration:
        duration = raw_duration // 1000 if raw_duration > 1000 else raw_duration
    return {
        "url": f"https://www.douyin.com/video/{aweme_id}/",
        "title": title,
        "thumbnail": thumbnail,
        "media_type": "video",
        "duration": duration,
        "image_count": 0,
        "post_time": post_time,
        "aweme_id": aweme_id,
        "author": author,
        "author_id": author_id,
    }


def fetch_user_post_list_via_browser(
    sec_uid: str,
    limit: int = 30,
    timeout: int = 180,
    user_data_dir: Optional[Path] = None,
    executable_path: Optional[str] = None,
    chromium_args: Optional[list[str]] = None,
    callback=None,
    should_stop=None,
) -> tuple[list[dict], str, bool, Optional[str]]:
    """用真实浏览器拦截主页作品列表，返回 (items, next_cursor, has_more, error)。

    思路与单条详情拦截相同：打开博主主页，让页面自己的 JS 走完
    Argus 验证并签名作品列表请求，拦截 /aweme/v1/web/aweme/post/
    的 200 响应；滚动页面触发翻页（服务端 max_cursor 链），直到
    凑够 limit 条或 has_more 为 false，不一次拉全量。

    Args:
        sec_uid: 主页 sec_uid（douyin.com/user/ 后面的那串）。
        limit: 最多返回条数（默认 30；首屏一页通常不足 30 条，
            内部会滚动翻页补齐）。
        timeout: 总等待时长（秒），超时返回已拿到的数据。
        user_data_dir / executable_path / chromium_args：同
            fetch_aweme_detail_via_browser。
        callback: 可选进度回调 callback(current, total)。
        should_stop: 可选取消回调，返回 True 时提前结束。

    Returns:
        (items, next_cursor, has_more, error)：items 为
        parse_user_post_aweme 的 dict 列表；next_cursor 为最后
        一页的 max_cursor（has_more 为 false 时为空串）；
        error 非空表示拿不到列表（私密主页/无权访问/需要登录/
        风控拦截/接口报错），此时 items 为空——调用方应把
        error 展示出来，不要当成"0 作品"静默处理。
        Playwright 未安装时返回 ([], "", False, error)。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "抖音主页列表不可用：未安装 Playwright，"
            "请执行 pip install lumio[browser] 后重试"
        )
        return [], "", False, "浏览器组件未安装：请执行 pip install lumio[browser] 后重试"

    profile_dir = Path(user_data_dir) if user_data_dir else _default_user_data_dir()
    state: dict[str, object] = {
        "items": [],
        "seen": set(),
        "max_cursor": "",
        "has_more": True,
        "responded": False,
        "empty_responses": 0,
        "api_error": None,
    }

    def _on_response(resp) -> None:
        # 调试用：主页实际请求的 aweme/v1/web 接口（默认 debug 关闭，零成本）
        if "/aweme/v1/web/" in resp.url:
            logger.debug("抖音主页响应 %s %s", resp.status, resp.url[:160])
        if _POST_LIST_URL_MARK not in resp.url:
            return
        if resp.status != 200:
            return
        # 200 即算响应：抖音风控时列表接口会返回 200 空体（非 JSON），
        # 此时 resp.json() 会抛错；若不标记 responded，首轮等待会
        # 烧光整个 timeout 且永远进不了滚动翻页。空体只记数。
        state["responded"] = True
        try:
            data = resp.json()
        except Exception:
            state["empty_responses"] = int(state["empty_responses"]) + 1
            return
        if data.get("status_code") != 0:
            msg = data.get("status_msg") or ""
            state["api_error"] = msg or (
                f"作品列表接口返回 status_code={data.get('status_code')}"
            )
            return
        items = state["items"]
        seen = state["seen"]
        for aw in data.get("aweme_list", []) or []:
            item = parse_user_post_aweme(aw)
            if item is not None and item["aweme_id"] not in seen:
                seen.add(item["aweme_id"])
                items.append(item)
        mc = data.get("max_cursor")
        if mc is not None:
            state["max_cursor"] = str(mc)
        hm = data.get("has_more")
        if hm is not None:
            state["has_more"] = bool(hm)
        if callback is not None:
            try:
                callback(len(items), limit)
            except Exception:
                pass

    page_text = ""
    try:
        with sync_playwright() as p:
            launch_kwargs: dict = {"headless": True}
            exe = executable_path
            if not exe:
                try:
                    managed = Path(p.chromium.executable_path)
                except Exception:
                    managed = None
                if managed is not None and managed.exists():
                    exe = None
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
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', "
                    "{ get: () => undefined })"
                )
                page = context.new_page()
                page.on("response", _on_response)
                user_url = _USER_PAGE_URL.format(sec_uid)
                try:
                    page.goto(user_url, wait_until="commit", timeout=30_000)
                except Exception as e:
                    logger.debug("抖音主页跳转未完成 %s，继续等待捕获：%s", user_url, e)
                deadline = time.monotonic() + timeout
                # 等首个列表响应（冷会话下页面 JS 验证可能耗时较久），
                # 但最多等 60 秒：即使首个响应是空体或还没来，也要进
                # 滚动翻页（后续请求可能成功），不要烧光整个 timeout。
                first_wait_end = min(deadline, time.monotonic() + 60)
                while (
                    time.monotonic() < first_wait_end
                    and not state["responded"]
                    and not state["api_error"]
                ):
                    if should_stop is not None and should_stop():
                        break
                    page.wait_for_timeout(1000)
                # 滚动翻页：直到凑够 limit、has_more 为 false、
                # 连续 3 次滚动无新条目，或超时/取消
                no_progress = 0
                while (
                    time.monotonic() < deadline
                    and len(state["items"]) < limit
                    and state["has_more"]
                    and not state["api_error"]
                ):
                    if should_stop is not None and should_stop():
                        break
                    before = len(state["items"])
                    try:
                        page.evaluate(
                            """() => {
                              const cands = [document.scrollingElement];
                              document.querySelectorAll('*').forEach(e => {
                                if (e.scrollHeight > e.clientHeight + 50) cands.push(e);
                              });
                              let best = null;
                              for (const e of cands) {
                                if (!e) continue;
                                if (!best || e.scrollHeight > best.scrollHeight) best = e;
                              }
                              if (best) best.scrollTop = best.scrollHeight;
                              window.scrollTo(0, document.body.scrollHeight);
                            }"""
                        )
                    except Exception:
                        pass
                    waited = 0
                    while (
                        waited < 5000
                        and len(state["items"]) == before
                        and time.monotonic() < deadline
                    ):
                        page.wait_for_timeout(500)
                        waited += 500
                    if len(state["items"]) == before:
                        no_progress += 1
                        if no_progress >= 3:
                            break
                    else:
                        no_progress = 0
                try:
                    page_text = page.inner_text("body") or ""
                except Exception:
                    page_text = ""
            finally:
                context.close()
    except Exception as e:
        logger.warning("抖音主页列表拦截失败（sec_uid=%s）：%s", sec_uid[:20], e)
        return [], "", False, f"浏览器打开主页失败：{e}"

    items = list(state["items"])[:limit]
    if items:
        next_cursor = str(state["max_cursor"]) if state["has_more"] else ""
        return items, next_cursor, bool(state["has_more"]), None
    if state["api_error"]:
        return [], "", False, f"抖音作品列表接口错误：{state['api_error']}"
    if not state["responded"]:
        return (
            [],
            "",
            False,
            "未能获取主页作品列表：未捕获到作品列表接口响应"
            "（可能触发风控、需要登录，或主页不存在）",
        )
    if int(state["empty_responses"]) > 0 and not state["items"]:
        return (
            [],
            "",
            False,
            "抖音作品列表接口返回空响应：服务器未返回作品数据"
            "（可能需要登录，或当前网络/会话触发风控）",
        )
    # 接口成功返回但 0 条：先看页面文本区分私密/注销/登录墙，
    # 都没有才认为是真实空主页
    if "用户不存在" in page_text:
        return [], "", False, "该用户不存在或主页链接无效"
    if any(m in page_text for m in ("设为私密", "私密账号", "私密帐户")):
        return [], "", False, "该账号已设为私密，无法查看作品列表"
    if "登录" in page_text and any(
        m in page_text for m in ("验证码", "扫码", "密码登录")
    ):
        return [], "", False, "查看该主页需要登录，请先登录抖音后再试"
    return [], "", False, None
