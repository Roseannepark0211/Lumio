from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..models import Base

_DB_PATH = Path.home() / ".getvp" / "library.db"

_engine = None
_session_factory = None


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
    engine = get_engine()
    Base.metadata.create_all(engine)
