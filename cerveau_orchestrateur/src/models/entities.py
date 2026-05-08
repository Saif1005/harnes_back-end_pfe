"""Modèles SQLAlchemy : auth + mémoire multi-agent."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    short_memories: Mapped[list["ShortTermMemory"]] = relationship(back_populates="user")
    long_memories: Mapped[list["LongTermMemory"]] = relationship(back_populates="user")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    short_memories: Mapped[list["ShortTermMemory"]] = relationship(back_populates="session")


class ShortTermMemory(Base):
    __tablename__ = "short_term_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_sessions.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(32))  # user | assistant | system | tool
    content: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User | None] = relationship(back_populates="short_memories")
    session: Mapped[AgentSession] = relationship(back_populates="short_memories")


class LongTermMemory(Base):
    __tablename__ = "long_term_memories"
    __table_args__ = (UniqueConstraint("user_id", "namespace", "memory_key", name="uq_long_term_memory"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    namespace: Mapped[str] = mapped_column(String(120), default="global")
    memory_key: Mapped[str] = mapped_column(String(255), index=True)
    memory_value: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User | None] = relationship(back_populates="long_memories")


class ERPConfig(Base):
    __tablename__ = "erp_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    db_type: Mapped[str] = mapped_column(String(32), default="postgresql")
    host: Mapped[str] = mapped_column(String(255), default="")
    port: Mapped[int] = mapped_column(Integer, default=5432)
    db_name: Mapped[str] = mapped_column(String(255), default="")
    username: Mapped[str] = mapped_column(String(255), default="")
    password: Mapped[str] = mapped_column(String(1024), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WarehouseInventoryRecord(Base):
    __tablename__ = "warehouse_inventory_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    source_file: Mapped[str] = mapped_column(String(255), default="")
    id_article_erp: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    categorie: Mapped[str] = mapped_column(String(255), default="")
    stage1_mp_pdr: Mapped[str] = mapped_column(String(32), default="")
    stage2_mp_chimie: Mapped[str] = mapped_column(String(32), default="")
    final_label: Mapped[str] = mapped_column(String(32), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WarehouseStockSnapshot(Base):
    __tablename__ = "warehouse_stock_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    source_file: Mapped[str] = mapped_column(String(255), default="")
    snapshot_date: Mapped[str] = mapped_column(String(32), default="")
    id_article_erp: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    categorie: Mapped[str] = mapped_column(String(255), default="")
    stock_quantity_kg: Mapped[float] = mapped_column(Float, default=0.0)
    stage1_mp_pdr: Mapped[str] = mapped_column(String(32), default="")
    stage2_mp_chimie: Mapped[str] = mapped_column(String(32), default="")
    final_label: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

