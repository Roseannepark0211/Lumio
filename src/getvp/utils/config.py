import os
import json
from pathlib import Path

_APP_DIR = Path.home() / ".getvp"
_CONFIG_FILE = _APP_DIR / "config.json"
_QUEUE_FILE = _APP_DIR / "queue.json"

DEFAULTS = {
    "download_dir": str(Path.home() / "Downloads" / "Lumio"),
    "cookie_file": str(_APP_DIR / "cookies.txt"),
    "init_completed": False,
    "cookie_banner_shown": False,
    "max_concurrent": 3,
    "max_retries": 3,
    "lang": "zh",
}


def _ensure_dir() -> None:
    _APP_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def save_config(cfg: dict) -> None:
    _ensure_dir()
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_cookie_path() -> Path | None:
    p = Path(load_config()["cookie_file"])
    return p if p.exists() else None


def get_download_dir() -> Path:
    return Path(load_config()["download_dir"])


def get_queue_path() -> Path:
    return _QUEUE_FILE
