from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ..models import Base

_DB_PATH = Path.home() / ".lumio" / "library.db"

_engine = None
_session_factory = None

logger = logging.getLogger(__name__)

# ============================================================
# Schema 迁移机制（PRAGMA user_version）
# ============================================================
#
# 设计原则（AGENTS.md "L4 数据级不变" + 自动更新可回滚）：
#   1. 只做加字段（ADD COLUMN），不做删字段/改类型，确保旧版本能读新 schema
#   2. 用 PRAGMA user_version 记录当前 schema 版本号
#   3. 每个迁移函数 idempotent（幂等），重复执行不报错
#   4. 迁移在事务中执行，失败则 ROLLBACK 保留旧版本
#   5. 新版本代码必须兼容旧 schema（缺字段时用默认值）
#
# 版本号约定：
#   0   — 初始版本（Base.metadata.create_all 创建的 schema）
#   1+  — 后续迁移版本号，递增
#
# 添加新迁移的步骤：
#   1. 在 _MIGRATIONS 数组末尾加一个迁移函数（命名为 migrate_vN_to_vN1）
#   2. 函数内用 op.execute("ALTER TABLE ...") 或 raw SQL
#   3. 不要忘记更新 _MIGRATIONS 数组


def _get_user_version(conn) -> int:
    """读取当前 schema 版本号（PRAGMA user_version）。"""
    result = conn.execute(text("PRAGMA user_version"))
    return int(result.fetchone()[0] or 0)


def _set_user_version(conn, version: int) -> None:
    """设置 schema 版本号（PRAGMA user_version = N）。"""
    conn.execute(text(f"PRAGMA user_version = {version}"))


def _migrate_v0_to_v1(conn) -> None:
    """v0 → v1: 占位迁移（示例，实际无字段变更）。

    保留此函数作为模板，未来真正需要迁移时复制改名即可。
    幂等性：ADD COLUMN 失败（字段已存在）时忽略错误。
    """
    # 示例（未启用）：
    # try:
    #     conn.execute(text("ALTER TABLE library_items ADD COLUMN new_field TEXT DEFAULT ''"))
    # except Exception:
    #     pass  # 字段已存在，幂等
    pass


# 迁移函数列表（按版本号顺序排列，index 0 = v0→v1, index 1 = v1→v2, ...）
_MIGRATIONS = [
    _migrate_v0_to_v1,
]


def _run_migrations(engine) -> None:
    """执行所有待应用的 schema 迁移。

    流程：
      1. 读取 PRAGMA user_version = N
      2. 依次执行 _MIGRATIONS[N], _MIGRATIONS[N+1], ...
      3. 每个迁移执行后立即更新 user_version
      4. 单个迁移失败则回滚事务并停止（保留旧版本，下次启动重试）
    """
    with engine.begin() as conn:
        current_version = _get_user_version(conn)
        target_version = len(_MIGRATIONS)

        if current_version >= target_version:
            # 已是最新版本，无需迁移
            return

        logger.info("DB schema migration: v%d → v%d", current_version, target_version)

        for i in range(current_version, target_version):
            migration_fn = _MIGRATIONS[i]
            from_version = i
            to_version = i + 1
            try:
                logger.info("Applying migration v%d → v%d (%s)", from_version, to_version, migration_fn.__name__)
                migration_fn(conn)
                _set_user_version(conn, to_version)
                conn.commit()
                logger.info("Migration v%d → v%d done", from_version, to_version)
            except Exception as e:
                conn.rollback()
                logger.error("Migration v%d → v%d FAILED: %s", from_version, to_version, e)
                # 不抛出，让应用继续启动（旧 schema 仍可用）
                # user_version 保持旧值，下次启动会重试
                break


def get_engine():
    global _engine
    if _engine is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory


def init_db():
    """初始化数据库：建表 + 执行 schema 迁移。

    流程：
      1. Base.metadata.create_all 创建新表（已存在的表不受影响）
      2. _run_migrations 执行 PRAGMA user_version 版本化迁移
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)
