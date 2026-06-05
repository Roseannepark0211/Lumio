import json
from pathlib import Path

_APP_DIR = Path.home() / ".lumio"
_CONFIG_FILE = _APP_DIR / "config.json"
_QUEUE_FILE = _APP_DIR / "queue.json"
_HISTORY_FILE = _APP_DIR / "history.json"

DEFAULTS = {
    "download_dir": str(Path.home() / "Downloads" / "Lumio"),
    "cookie_file": str(_APP_DIR / "cookies.txt"),
    "init_completed": False,
    "cookie_banner_shown": False,
    "max_concurrent": 3,
    "max_retries": 3,
    "lang": "zh",
    "theme": "dark",
    "storage_mode": "simple",
    "file_conflict_policy": "rename",
}

_cache: dict | None = None


def _ensure_dir() -> None:
    _APP_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    cfg = dict(DEFAULTS)
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    _cache = cfg
    return cfg


def save_config(cfg: dict) -> None:
    global _cache
    _ensure_dir()
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    _cache = cfg


def get_cookie_path() -> Path | None:
    cookie_file = load_config().get("cookie_file") or str(_APP_DIR / "cookies.txt")
    p = Path(cookie_file)
    return p if p.exists() else None


def get_download_dir() -> Path:
    return Path(load_config()["download_dir"])


def get_storage_mode() -> str:
    return load_config().get("storage_mode", "simple")


def get_file_conflict_policy() -> str:
    return load_config().get("file_conflict_policy", "rename")


def get_queue_path() -> Path:
    return _QUEUE_FILE


def get_history_path() -> Path:
    return _HISTORY_FILE


def get_library_db_path() -> Path:
    return _APP_DIR / "library.db"


def get_thumbs_dir() -> Path:
    d = _APP_DIR / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d
