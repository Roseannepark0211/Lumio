"""通知清理与精简的回归测试。

覆盖 2026-10-26 通知后端修复：
- _PYTHON_DEPS 剔除已剥离的 PySide6 与无用的 packaging
- _remove_by_source_key 合并为唯一定义，删除落盘且重读消失
- ffmpeg/cookie 删除分支（条件消失即清理旧通知）
- version_new 只留一句话摘要，不再贴千字 release body
- 周期/手动检查确认最新时不再创建常驻 version_latest 条目
- 后端 toast key cache_cleaned_toast 补齐；t() 缺 key 记 warning
"""
import json
import logging

import lumio.notification_manager as nm
from lumio.notification_manager import NotificationManager, _PYTHON_DEPS


def _seed_mgr(tmp_path, monkeypatch, records):
    f = tmp_path / "notifications.json"
    f.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(nm, "_NOTIF_FILE", f)
    return NotificationManager(), f


def _rec(source_key, **kw):
    d = {
        "id": "id-" + source_key,
        "category": "deps",
        "type": "warning",
        "title": "t",
        "message": "m",
        "action": "",
        "action_text": "",
        "created_at": "2026-10-20T00:00:00+00:00",
        "read": False,
        "source_key": source_key,
        "dismissable": True,
        "priority": "normal",
        "expires_at": "",
        "group_key": "",
    }
    d.update(kw)
    return d


def _mock_config(monkeypatch):
    import lumio.utils.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "load_config", lambda: {})
    monkeypatch.setattr(cfg_mod, "save_config", lambda cfg: None)


def test_python_deps_pruned():
    """检查单不再含已剥离的 PySide6 与无用的 packaging。"""
    assert "PySide6" not in _PYTHON_DEPS
    assert "packaging" not in _PYTHON_DEPS
    assert {"yt_dlp", "flask", "sqlalchemy", "PIL",
            "apify_client", "imageio_ffmpeg", "requests"} <= set(_PYTHON_DEPS)


def test_remove_by_source_key_persists_and_reloads(tmp_path, monkeypatch):
    """删除后落盘，且新实例重读后该记录确实消失（旧重复定义只改内存不保存）。"""
    mgr, f = _seed_mgr(tmp_path, monkeypatch,
                       [_rec("python_deps_missing"), _rec("proxy_missing")])
    assert len(mgr.get_all()) == 2
    mgr._remove_by_source_key("python_deps_missing")
    assert [n.source_key for n in mgr.get_all()] == ["proxy_missing"]
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert [d["source_key"] for d in saved] == ["proxy_missing"]
    mgr2 = NotificationManager()
    assert [n.source_key for n in mgr2.get_all()] == ["proxy_missing"]


def test_ffmpeg_delete_branch(tmp_path, monkeypatch):
    """找到 FFmpeg 时清理之前发的 ffmpeg_missing 通知。"""
    import lumio.downloader as dl_mod
    monkeypatch.setattr(dl_mod, "_find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    mgr, _ = _seed_mgr(tmp_path, monkeypatch, [_rec("ffmpeg_missing")])
    mgr._check_ffmpeg()
    assert "ffmpeg_missing" not in [n.source_key for n in mgr.get_all()]


def test_cookie_delete_branches(tmp_path, monkeypatch):
    """Cookie 全部正常时清理 cookie_missing 与 cookie_expiring 旧通知。"""
    import lumio.utils.cookie_checker as cc_mod
    for name in ("check_ig_cookie_status", "check_x_cookie_status",
                 "check_yt_cookie_status", "check_douyin_cookie_status",
                 "check_xiaohongshu_cookie_status", "check_bilibili_cookie_status",
                 "check_kuaishou_cookie_status"):
        monkeypatch.setattr(cc_mod, name, lambda: "valid")
    mgr, _ = _seed_mgr(tmp_path, monkeypatch,
                       [_rec("cookie_missing"), _rec("cookie_expiring")])
    mgr._check_cookies()
    keys = [n.source_key for n in mgr.get_all()]
    assert "cookie_missing" not in keys
    assert "cookie_expiring" not in keys


def test_version_new_message_is_short_summary(tmp_path, monkeypatch):
    """version_new 不再贴千字 release body，只留一句话摘要，跳转动作不变。"""
    import lumio.i18n as i18n_mod
    monkeypatch.setattr(i18n_mod, "_LANG", "zh")
    _mock_config(monkeypatch)
    mgr, _ = _seed_mgr(tmp_path, monkeypatch, [])
    monkeypatch.setattr(NotificationManager, "_do_version_check",
                        lambda self: "new:9.9.9")
    mgr._latest_release_body = "x" * 5000
    mgr._latest_release_name = "Big Release"
    mgr._check_version_periodic()
    items = [n for n in mgr.get_all() if n.source_key == "version_new"]
    assert len(items) == 1
    item = items[0]
    assert item.title == "Lumio 9.9.9 — Big Release"
    assert "x" * 100 not in item.message
    assert len(item.message) < 200
    assert item.action == "open_url:https://github.com/Roseannepark0211/Lumio/releases"


def test_periodic_check_latest_is_silent(tmp_path, monkeypatch):
    """周期检查确认最新时静默：不创建 version_latest，且清理旧条目。"""
    _mock_config(monkeypatch)
    mgr, _ = _seed_mgr(tmp_path, monkeypatch, [_rec("version_new")])
    monkeypatch.setattr(NotificationManager, "_do_version_check",
                        lambda self: "latest")
    mgr._check_version_periodic()
    keys = [n.source_key for n in mgr.get_all()]
    assert "version_latest" not in keys
    assert "version_new" not in keys


def test_manual_check_latest_creates_no_persistent_entry(tmp_path, monkeypatch):
    """手动检查确认最新时同样不创建常驻条目，但返回值仍是 latest。"""
    _mock_config(monkeypatch)
    mgr, _ = _seed_mgr(tmp_path, monkeypatch,
                       [_rec("version_new"), _rec("version_latest")])
    monkeypatch.setattr(NotificationManager, "_do_version_check",
                        lambda self: "latest")
    assert mgr.check_version_manual() == "latest"
    keys = [n.source_key for n in mgr.get_all()]
    assert "version_latest" not in keys
    assert "version_new" not in keys


def test_cache_cleaned_toast_key_and_missing_key_warning(monkeypatch, caplog):
    """补齐的 cache_cleaned_toast 中英文模板占位符对上；缺 key 记 warning。"""
    import lumio.i18n as i18n_mod
    monkeypatch.setattr(i18n_mod, "_LANG", "zh")
    assert i18n_mod.t("cache_cleaned_toast", 3, "12.5 MB") == \
        "缓存已清理：3 个文件，释放 12.5 MB"
    monkeypatch.setattr(i18n_mod, "_LANG", "en")
    assert i18n_mod.t("cache_cleaned_toast", 3, "12.5 MB") == \
        "Cache cleaned: 3 files, 12.5 MB freed"
    with caplog.at_level(logging.WARNING, logger="lumio.i18n"):
        out = i18n_mod.t("definitely_missing_key_xyz")
    assert out == "definitely_missing_key_xyz"
    assert "Missing i18n key" in caplog.text
