from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class LibraryItem(Base):
    __tablename__ = "library_items"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    title = Column(String, default="")
    author = Column(String, default="")
    platform = Column(String, default="")
    url = Column(String, default="")
    file_path = Column(String, default="")
    file_size = Column(Integer, default=0)
    media_type = Column(String, default="")
    duration = Column(Integer, nullable=True)
    post_time = Column(String, default="")
    thumbnail_url = Column(String, default="")
    local_thumbnail_path = Column(String, default="")
    is_favorite = Column(Boolean, default=False)
    folder_path = Column(String, default="")
    batch_id = Column(String, default="")
    content_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    item_collections = relationship("ItemCollection", back_populates="item", cascade="all, delete-orphan")


class Collection(Base):
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    icon = Column(String, default="📁")
    created_at = Column(DateTime, default=func.now())

    # Relationships
    item_collections = relationship("ItemCollection", back_populates="collection", cascade="all, delete-orphan")


class ItemCollection(Base):
    __tablename__ = "item_collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String, ForeignKey("library_items.id", ondelete="CASCADE"), nullable=False)
    collection_id = Column(Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)

    item = relationship("LibraryItem", back_populates="item_collections")
    collection = relationship("Collection", back_populates="item_collections")

    __table_args__ = (UniqueConstraint("item_id", "collection_id"),)
