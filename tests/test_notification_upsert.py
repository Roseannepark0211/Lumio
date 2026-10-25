"""同 source_key 通知 upsert 语义：已存记录的内容随代码更新。

回归场景（2026-10-25 真机实测）：Python 依赖通知在 v4.5.3 之前以
仓库地址存入 ~/.lumio/notifications.json；v4.5.3 把安装动作改指
python.org 后，旧版“已存在则跳过”的去重语义让老记录的旧动作永久
保留，新设备（无旧记录）却指向 python.org。upsert 后，启动检测
生成的最新内容会刷新已存记录。
"""
import json

import lumio.notification_manager as nm
from lumio.notification_manager import Notification, NotificationManager

OLD_ACTION = "open_url:https://github.com/Roseannepark0211/Lumio"
NEW_ACTION = "open_url:https://www.python.org/downloads/"


def _seed_file(tmp_path, records):
    f = tmp_path / "notifications.json"
    f.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return f


def test_upsert_refreshes_stored_action_and_persists(tmp_path, monkeypatch):
    """老记录（仓库地址）+ 新内容（python.org）→ 同一条记录被刷新并落盘。"""
    seed = [{
        "id": "old123",
        "category": "deps",
        "type": "warning",
        "title": "旧标题",
        "message": "旧文案",
        "action": OLD_ACTION,
        "action_text": "安装",
        "created_at": "2026-10-20T00:00:00+00:00",
        "read": True,
        "source_key": "python_deps_missing",
        "dismissable": True,
        "priority": "critical",
        "expires_at": "",
        "group_key": "",
    }]
    f = _seed_file(tmp_path, seed)
    monkeypatch.setattr(nm, "_NOTIF_FILE", f)

    mgr = NotificationManager()
    assert len(mgr.get_all()) == 1

    mgr.add_notification(Notification(
        category="deps",
        type="warning",
        priority="critical",
        title="新标题",
        message="新文案",
        action=NEW_ACTION,
        action_text="安装",
        source_key="python_deps_missing",
    ))

    items = mgr.get_all()
    assert len(items) == 1
    item = items[0]
    assert item.action == NEW_ACTION
    assert item.title == "新标题"
    # 身份与用户状态保留：不重复提醒、不换 id、不改首次出现时间
    assert item.id == "old123"
    assert item.read is True
    assert item.created_at == "2026-10-20T00:00:00+00:00"
    # 落盘内容同步刷新
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["action"] == NEW_ACTION


def test_empty_source_key_still_appends(tmp_path, monkeypatch):
    """无 source_key 的通知不参与去重，沿用追加语义。"""
    f = tmp_path / "notifications.json"
    monkeypatch.setattr(nm, "_NOTIF_FILE", f)
    mgr = NotificationManager()
    mgr.add_notification(Notification(title="a"))
    mgr.add_notification(Notification(title="b"))
    assert len(mgr.get_all()) == 2


def test_different_source_keys_append(tmp_path, monkeypatch):
    """不同 source_key 的通知互不干扰。"""
    f = tmp_path / "notifications.json"
    monkeypatch.setattr(nm, "_NOTIF_FILE", f)
    mgr = NotificationManager()
    mgr.add_notification(Notification(title="a", source_key="k1"))
    mgr.add_notification(Notification(title="b", source_key="k2"))
    assert len(mgr.get_all()) == 2
