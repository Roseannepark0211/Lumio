"""PySide6 Signal/QObject/QThread 的纯 Python 兼容层。

目的：让业务 manager (queue/library/inbox/notification/telegram) 不再依赖
PySide6，但仍保留 Signal 的 connect/emit API 形式，最小化改动 manager 代码。

兼容性：
- Signal(*types).connect(callback, Qt.DirectConnection)  ✓
- Signal(*types).emit(*args)                              ✓ 同步调用
- QObject 子类                                            ✓ 空基类
- QThread 子类（run/isRunning/wait/terminate）            ✓ 用 threading.Thread
- Qt.DirectConnection                                     ✓ 常量
- QApplication.instance()                                 ✓ 单例 placeholder

差异：
- 无 Qt event loop，所有 emit 同步执行 callback（等价 DirectConnection）
- QThread 用 threading.Thread 实现，无 Qt 信号调度
- 不支持 cross-thread queued connection（FastAPI 场景都是 DirectConnection）

替换策略：每个 manager 把 `from PySide6.QtCore import QObject, Signal`
改为 `from ..utils.signal import QObject, Signal`，其余代码不动。
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from typing import Any, Callable


# ============================================================
# Qt 常量
# ============================================================

class Qt:
    """Qt 命名空间常量（仅保留实际使用的）。"""
    DirectConnection = 5      # 兼容 PySide6.QtCore.Qt.DirectConnection
    QueuedConnection = 4      # 兼容 PySide6.QtCore.Qt.QueuedConnection
    AutoConnection = 3        # 兼容 PySide6.QtCore.Qt.AutoConnection


# ============================================================
# QObject 基类
# ============================================================

class QObject:
    """空 QObject 基类，仅作 placeholder。

    PySide6 的 QObject 提供 parent/children 管理、signal-threading 检查，
    这里都不需要。manager 子类继承它只是为了符合 PySide6 语法。

    接受可选 parent 参数兼容 PySide6 API（如 DownloadManager.__init__(parent)）。
    """

    def __init__(self, parent: "QObject | None" = None) -> None:
        # parent 仅作语法兼容，不做实际父子关系管理
        pass

    def moveToThread(self, thread: "QThread | None") -> None:
        """no-op — 兼容 PySide6 API。

        本兼容层 Signal 总是同步调用 callback（DirectConnection），
        不依赖线程亲和性，moveToThread 无实际效果。
        """
        pass

    def thread(self) -> "QThread | None":
        """no-op — 兼容 PySide6 API。返回 None 表示无亲和线程。"""
        return None


# ============================================================
# Signal
# ============================================================

class Signal:
    """PySide6.Signal 的纯 Python 实现。

    用法（与 PySide6 完全兼容）：
        class MyManager(QObject):
            item_added = Signal(str)
            progress = Signal(str, float)

            def do_work(self):
                self.item_added.emit("xxx")
                self.progress.emit("xxx", 0.5)

        m = MyManager()
        m.item_added.connect(lambda x: print(x), Qt.DirectConnection)
        m.do_work()  # 同步调用 callback

    差异：
    - 类型参数仅作 placeholder，不做运行时类型检查（PySide6 也不做）
    - emit 同步执行所有 callback（DirectConnection 语义）
    - 不支持 thread-affinity 检查（FastAPI 跨线程调用的就是 DirectConnection）
    """

    def __init__(self, *types: type) -> None:
        # 类型参数仅用于文档化，不做检查
        self._types = types
        self._name: str = ""
        self._callbacks: list[Callable[..., Any]] = []
        self._lock = threading.RLock()

    # PySide6 在类创建时通过 __set_name__ 设置 signal 名
    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def connect(
        self,
        callback: Callable[..., Any],
        connection_type: int = Qt.AutoConnection,
    ) -> None:
        """注册 callback。connection_type 参数兼容 PySide6 但被忽略
        （本实现总是同步调用，等价 DirectConnection）。"""
        with self._lock:
            self._callbacks.append(callback)

    def disconnect(self, callback: Callable[..., Any] = None) -> None:
        """移除 callback。callback=None 时清空所有。"""
        with self._lock:
            if callback is None:
                self._callbacks.clear()
            else:
                self._callbacks = [cb for cb in self._callbacks if cb is not callback]

    def emit(self, *args: Any) -> None:
        """同步调用所有 callback。异常会打印但不会中断后续 callback。"""
        # 复制一份避免持锁调用 callback（callback 可能再 connect 新的）
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(*args)
            except Exception:
                import traceback
                traceback.print_exc()


# ============================================================
# QThread
# ============================================================

class QThread(QObject):
    """PySide6.QThread 的纯 Python 实现，用 threading.Thread 替代。

    用法（与 PySide6 兼容）：
        class MyWorker(QThread):
            progress = Signal(int)

            def run(self):
                for i in range(100):
                    self.progress.emit(i)

        worker = MyWorker()
        worker.progress.connect(lambda p: print(p))
        worker.start()           # 非阻塞
        worker.wait()            # 阻塞等待结束

    差异：
    - 不支持 QThread.signal.connect(sender.signal) 跨线程连接
    - 不支持 terminate() 强制杀线程（用 daemon=True 让进程退出时自动结束）
    - isRunning() → is_alive()
    """

    def __init__(self, parent: QObject = None) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        # QThread.started/finished 在 PySide6 是 Signal，这里简化为 callback 列表
        self.started = _SignalLike()
        self.finished = _SignalLike()

    def run(self) -> None:
        """子类重写。默认什么都不做。"""
        pass

    def start(self, priority: int = 0) -> None:
        """启动线程。priority 参数兼容 PySide6 但被忽略。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_wrapper,
            name=f"{self.__class__.__name__}-{uuid.uuid4().hex[:8]}",
            daemon=True,
        )
        self._thread.start()

    def _run_wrapper(self) -> None:
        """线程入口：触发 started → run() → finished。"""
        self.started.emit()
        try:
            self.run()
        finally:
            self.finished.emit()

    def wait(self, timeout: int = 0xFFFFFFFF) -> bool:
        """阻塞等待线程结束。timeout 单位 ms（PySide6 兼容）。返回 True 表示已结束。"""
        if self._thread is None:
            return True
        if timeout == 0xFFFFFFFF:
            self._thread.join()
            return True
        # ms → s
        self._thread.join(timeout=timeout / 1000.0)
        return not self._thread.is_alive()

    def isRunning(self) -> bool:
        """PySide6 API 兼容。"""
        return self._thread is not None and self._thread.is_alive()

    def terminate(self) -> None:
        """PySide6 terminate 兼容。Python threading 不支持强制杀线程，此处 no-op。

        daemon=True 保证进程退出时线程自动结束。
        """
        # no-op — Python threading 不支持 terminate
        pass

    def quit(self) -> None:
        """PySide6 quit 兼容。no-op（threading 无法优雅停止 run()）。"""
        pass


class _SignalLike:
    """简化 Signal，用于 QThread.started/finished。"""

    def __init__(self) -> None:
        self._callbacks: list[Callable[..., Any]] = []

    def connect(self, callback: Callable[..., Any], *_a, **_kw) -> None:
        self._callbacks.append(callback)

    def emit(self, *args: Any) -> None:
        for cb in list(self._callbacks):
            try:
                cb(*args)
            except Exception:
                import traceback
                traceback.print_exc()


# ============================================================
# QApplication 单例 placeholder
# ============================================================

class QApplication:
    """QApplication 单例 placeholder。

    api_fastapi.py 中 `QApplication.instance() or QApplication(sys.argv)`
    创建 QApplication 实例，让 manager（QObject 子类）能正常实例化。
    实际 PySide6 的 QApplication 会启动 Qt event loop，这里不启动。

    FastAPI 路径不需要 Qt event loop：
    - Signal.emit 同步执行 callback（本兼容层实现）
    - QThread 用 threading.Thread（本兼容层实现）
    - manager 的 Signal 通过 _wire_signals 桥接到 EventBus，EventBus 用 asyncio
    """

    _instance: "QApplication | None" = None

    def __init__(self, argv: list[str] | None = None) -> None:
        # 单例：第二次构造时复用
        if QApplication._instance is not None:
            return
        QApplication._instance = self
        self._argv = argv or []

    @classmethod
    def instance(cls) -> "QApplication | None":
        return cls._instance

    def setQuitOnLastWindowClosed(self, flag: bool) -> None:
        """no-op — 无窗口系统。"""
        pass

    def exec(self) -> int:
        """no-op — 不启动 event loop。FastAPI 用 uvicorn.run 启动自己的 loop。"""
        return 0

    def quit(self) -> None:
        """no-op。"""
        pass


# ============================================================
# QGuiApplication / QDesktopServices / QUrl — api_fastapi.py 用
# ============================================================

class QGuiApplication(QApplication):
    """QGuiApplication placeholder，用于 clipboard 访问。"""
    pass


class _QGuiApplicationClipboard:
    """QGuiApplication.clipboard() 占位 — 跨平台剪贴板访问。

    - Windows: 用 ctypes.windll（user32/kernel32）直接调 Win32 API
    - macOS: 用 pbcopy/pbpaste 命令
    - Linux: 优先 xclip，回退 xsel
    """

    def text(self) -> str:
        try:
            if sys.platform == "win32":
                return self._text_win32()
            elif sys.platform == "darwin":
                return self._text_macos()
            else:
                return self._text_linux()
        except Exception:
            return ""

    def setText(self, text: str) -> None:
        try:
            if sys.platform == "win32":
                self._set_text_win32(text)
            elif sys.platform == "darwin":
                self._set_text_macos(text)
            else:
                self._set_text_linux(text)
        except Exception:
            pass

    # ---------- Windows ----------

    @staticmethod
    def _text_win32() -> str:
        # 关键：64 位 Windows 上 ctypes 默认 restype=c_int（32 位），
        # 但 GetClipboardData / GlobalLock 返回 HGLOBAL/HANDLE（64 位指针），
        # 高 32 位被截断 → 访问违例 0xC0000005 崩溃。
        # 必须设置 restype=c_void_p（64 位指针）才能正确接收返回值。
        import ctypes
        from ctypes import wintypes
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        # 设置函数签名（避免 64 位指针被截断）
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE  # 64 位指针
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID  # 64 位指针
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        if not user32.OpenClipboard(0):
            # 剪贴板被其他程序锁定，重试 3 次（间隔 50ms）
            import time
            for _ in range(3):
                time.sleep(0.05)
                if user32.OpenClipboard(0):
                    break
            else:
                return ""
        try:
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return ""
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            # CF_UNICODETEXT 返回的 handle 是 GlobalMem，需 GlobalLock 获取指针
            # 锁定后读取宽字符串，再解锁（必须配对，否则内存泄漏）
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                # c_wchar_p 从指针读取以 null 结尾的宽字符串
                text = ctypes.cast(ptr, ctypes.c_wchar_p).value or ""
                return text
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    @staticmethod
    def _set_text_win32(text: str) -> None:
        import ctypes
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.OpenClipboard(0)
        try:
            user32.EmptyClipboard()
            if text:
                # GlobalAlloc(GMEM_MOVEABLE, len * 2 + 2)
                GMEM_MOVEABLE = 0x0002
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                buf = ctypes.create_unicode_buffer(text)
                size = len(text) + 1
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, size * 2)
                if h_mem:
                    locked = kernel32.GlobalLock(h_mem)
                    if locked:
                        ctypes.memmove(locked, buf, size * 2)
                        kernel32.GlobalUnlock(h_mem)
                        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        finally:
            user32.CloseClipboard()

    # ---------- macOS ----------

    @staticmethod
    def _text_macos() -> str:
        import subprocess
        result = subprocess.run(
            ["pbpaste", "-Prefer", "txt"],
            capture_output=True, text=True, check=False,
        )
        return result.stdout

    @staticmethod
    def _set_text_macos(text: str) -> None:
        import subprocess
        subprocess.run(
            ["pbcopy"],
            input=text, text=True, check=False,
        )

    # ---------- Linux ----------

    @staticmethod
    def _text_linux() -> str:
        import subprocess
        import shutil
        if shutil.which("xclip"):
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True, text=True, check=False,
            )
            return result.stdout
        if shutil.which("xsel"):
            result = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                capture_output=True, text=True, check=False,
            )
            return result.stdout
        return ""

    @staticmethod
    def _set_text_linux(text: str) -> None:
        import subprocess
        import shutil
        if shutil.which("xclip"):
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text, text=True, check=False,
            )
        elif shutil.which("xsel"):
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text, text=True, check=False,
            )


def _qgui_clipboard() -> _QGuiApplicationClipboard:
    return _QGuiApplicationClipboard()


# 让 QGuiApplication.clipboard() 可作为方法调用
def _clipboard_classmethod() -> _QGuiApplicationClipboard:
    return _qgui_clipboard()


class QDesktopServices:
    """QDesktopServices placeholder，跨平台打开 URL/文件。"""

    @staticmethod
    def openUrl(url: Any) -> bool:
        """打开 URL 或文件路径。url 可以是 str 或 QUrl。"""
        url_str = str(url)
        # 去掉 QUrl 的 file:/// 前缀对本地路径的处理
        if url_str.startswith("file:///"):
            # Windows: file:///C:/path → C:\path
            # macOS/Linux: file:///path → /path
            url_str = url_str[8:]
            if sys.platform == "win32":
                url_str = url_str.replace("/", "\\")
        try:
            import os
            import subprocess
            if url_str.startswith(("http://", "https://")):
                # 用默认浏览器打开 URL（跨平台）
                if sys.platform == "win32":
                    subprocess.Popen(["cmd", "/c", "start", "", url_str], shell=False)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", url_str])
                else:
                    subprocess.Popen(["xdg-open", url_str])
            else:
                # 本地文件/目录（跨平台）
                if os.path.exists(url_str):
                    if sys.platform == "win32":
                        os.startfile(url_str)  # type: ignore[attr-defined]
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", url_str])
                    else:
                        subprocess.Popen(["xdg-open", url_str])
            return True
        except Exception:
            return False


class QUrl:
    """QUrl placeholder — api_fastapi.py 中用 QUrl(url) 仅作 URL 容器。"""

    def __init__(self, url: str = "") -> None:
        self._url = url

    def toString(self) -> str:
        return self._url

    def __str__(self) -> str:
        return self._url

    @classmethod
    def fromLocalFile(cls, path: str) -> "QUrl":
        import os
        # 简单转 file:/// URL
        abs_path = os.path.abspath(path).replace("\\", "/")
        return cls(f"file:///{abs_path}")
