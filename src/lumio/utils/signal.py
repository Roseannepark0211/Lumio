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
    """
    pass


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
    """QGuiApplication.clipboard() 占位 — 实际剪贴板访问用 ctypes/pyperclip。"""

    def text(self) -> str:
        try:
            import ctypes
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            user32.OpenClipboard(0)
            try:
                if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    return ""
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                ptr = ctypes.cast(handle, ctypes.c_wchar_p)
                return ptr.value or ""
            finally:
                user32.CloseClipboard()
        except Exception:
            return ""

    def setText(self, text: str) -> None:
        try:
            import ctypes
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            user32.OpenClipboard(0)
            try:
                user32.EmptyClipboard()
                if text:
                    # GlobalAlloc(GMEM_MOVEABLE, len * 2 + 2)
                    GMEM_MOVEABLE = 0x0002
                    kernel32 = ctypes.windll.kernel32
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
        except Exception:
            pass


def _qgui_clipboard() -> _QGuiApplicationClipboard:
    return _QGuiApplicationClipboard()


# 让 QGuiApplication.clipboard() 可作为方法调用
def _clipboard_classmethod() -> _QGuiApplicationClipboard:
    return _qgui_clipboard()


class QDesktopServices:
    """QDesktopServices placeholder，用 os.startfile/subprocess 替代。"""

    @staticmethod
    def openUrl(url: Any) -> bool:
        """打开 URL 或文件路径。url 可以是 str 或 QUrl。"""
        url_str = str(url)
        # 去掉 QUrl 的 file:/// 或 http:// 前缀对本地路径的处理
        if url_str.startswith("file:///"):
            url_str = url_str[8:].replace("/", "\\")
        try:
            import os
            import subprocess
            if url_str.startswith(("http://", "https://")):
                # 用默认浏览器打开 URL
                subprocess.Popen(["cmd", "/c", "start", "", url_str], shell=False)
            else:
                # 本地文件/目录
                if os.path.exists(url_str):
                    os.startfile(url_str)
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
