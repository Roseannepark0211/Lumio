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
    "theme": "light",
    "storage_mode": "simple",
    "file_conflict_policy": "rename",
    "auto_download_inbox": False,
    "enable_xsou": False,  # X-Sou 搜索默认关闭（可能浏览到 18+ 内容，需用户显式启用）
    # 关闭主窗口时的行为：ask(每次询问) / minimize(总是最小化到托盘) / quit(总是退出程序)
    # 由 Electron main.ts 的 close 事件读取；用户在 close-dialog 勾选「记住选择」时写入
    "close_behavior": "ask",
    "api_port": 38900,
    "telegram_bot_token": "",
    "telegram_enabled": False,
    "telegram_poll_interval": 10,
    "telegram_api_base": "https://api.telegram.org",
    # Platform credentials
    "apify_token": "",
    "apify_ig_actor": "",
    "apify_verified": False,  # Token 是否已验证有效（输入框变化时自动清除，验证成功时置 True）
    "instagram_mode": "cookie",   # "cookie" | "api"
    "x_mode": "cookie",           # "cookie" | "api"
    "youtube_mode": "cookie",     # "cookie" | "api"
    # Cache management
    "cache_management": {
        "auto_clean": "off",          # "off" | "startup" | "daily" | "weekly"
        "retain_days": 7,             # 保留最近 N 天
        "max_size_mb": 500,           # 单目录上限（MB）
        "last_cleaned": "",           # ISO 时间戳，记录上次清理时间
    },
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
        # utf-8-sig 自动剥离 BOM：config.json 可能被外部编辑器/QML 侧写入带 BOM，
        # 普通 utf-8 解码会让 json.load 抛 JSONDecodeError，FastAPI 启动失败。
        with open(_CONFIG_FILE, encoding="utf-8-sig") as f:
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
    """返回用户 cookie 文件路径，无效时返回 None。

    判定无效的情况（避免 yt-dlp / MozillaCookieJar 报错）：
    - 文件不存在
    - 文件为空（0 字节）
    - 文件不以 Netscape 格式 cookie header 开头
      （Netscape 格式首行通常是 # Netscape HTTP Cookie File 或注释行 # ...）
    """
    cookie_file = load_config().get("cookie_file") or str(_APP_DIR / "cookies.txt")
    p = Path(cookie_file)
    if not p.exists():
        return None
    # 空文件无效（yt-dlp 会报 "does not look like a Netscape format cookies file"）
    if p.stat().st_size == 0:
        return None
    # 非 Netscape 格式无效（首字符必须是 #，Netscape 格式以注释行开头）
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
        if not first_line.startswith("#"):
            return None
    except Exception:
        return None
    return p


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


def get_platform_mode(platform: str) -> str:
    """Return 'cookie' or 'api' for the given platform ('instagram', 'x', 'youtube')."""
    return load_config().get(f"{platform}_mode", "cookie")


def get_apify_token() -> str:
    return load_config().get("apify_token", "")
