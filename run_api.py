"""PyInstaller entry point for Lumio FastAPI backend.

Electron + React 前端通过 spawn 子进程启动这个后端。
原 run.py 指向已删除的 lumio.main:main（QML 入口），此文件替代它。
"""
from lumio.api_fastapi import main

if __name__ == "__main__":
    main()
