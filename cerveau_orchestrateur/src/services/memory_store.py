"""Stockage mémoire short-term et long-term."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.entities import AgentSession, LongTermMemory, ShortTermMemory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_session(db: Session, *, session_id: str, user_id: str | None, title: str = "") -> AgentSession:
    session = db.get(AgentSession, session_id)
    if session is None:
        session = AgentSession(id=session_id, user_id=user_id, title=title or "Session opérateur")
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session.updated_at = _utcnow()
        if user_id and not session.user_id:
            session.user_id = user_id
        if title and not session.title:
            session.title = title
        db.commit()
    return session


def generate_session_id() -> str:
    return f"sess-{uuid.uuid4().hex[:16]}"


def append_short_term_memory(
    db: Session,
    *,
    session_id: str,
    user_id: str | None,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> ShortTermMemory:
    ensure_session(db, session_id=session_id, user_id=user_id)
    turn_index = (
        db.execute(select(func.coalesce(func.max(ShortTermMemory.turn_index), 0)).where(ShortTermMemory.session_id == session_id))
        .scalar_one()
        + 1
    )
    row = ShortTermMemory(
        session_id=session_id,
        user_id=user_id,
        turn_index=int(turn_index),
        role=role,
        content=content,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_short_term_memories(
    db: Session,
    *,
    session_id: str,
    user_id: str | None,
    limit: int = 30,
) -> list[ShortTermMemory]:
    query = select(ShortTermMemory).where(ShortTermMemory.session_id == session_id)
    if user_id:
        query = query.where((ShortTermMemory.user_id == user_id) | (ShortTermMemory.user_id.is_(None)))
    query = query.order_by(ShortTermMemory.turn_index.desc()).limit(limit)
    rows = list(db.execute(query).scalars().all())
    rows.reverse()
    return rows


def upsert_long_term_memory(
    db: Session,
    *,
    user_id: str | None,
    namespace: str,
    memory_key: str,
    memory_value: str,
    score: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> LongTermMemory:
    stmt = select(LongTermMemory).where(
        LongTermMemory.user_id == user_id,
        LongTermMemory.namespace == namespace,
        LongTermMemory.memory_key == memory_key,
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        row = LongTermMemory(
            user_id=user_id,
            namespace=namespace,
            memory_key=memory_key,
            memory_value=memory_value,
            score=score,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        db.add(row)
    else:
        row.memory_value = memory_value
        row.score = score
        row.metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def list_long_term_memories(
    db: Session,
    *,
    user_id: str | None,
    namespace: str = "",
    limit: int = 50,
) -> list[LongTermMemory]:
    query = select(LongTermMemory)
    if user_id:
        query = query.where((LongTermMemory.user_id == user_id) | (LongTermMemory.user_id.is_(None)))
    if namespace:
        query = query.where(LongTermMemory.namespace == namespace)
    query = query.order_by(LongTermMemory.updated_at.desc()).limit(limit)
    return list(db.execute(query).scalars().all())


def record_ask_agent_turn(
    db: Session,
    *,
    user_id: str | None,
    session_id: str,
    question: str,
    response: str,
    route_intent: str,
    article_id: str,
) -> None:
    append_short_term_memory(
        db,
        session_id=session_id,
        user_id=user_id,
        role="user",
        content=question,
        metadata={"source": "ask_agent", "article_id": article_id},
    )
    append_short_term_memory(
        db,
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        content=response,
        metadata={"source": "ask_agent", "route_intent": route_intent, "article_id": article_id},
    )
    upsert_long_term_memory(
        db,
        user_id=user_id,
        namespace="operator_preferences",
        memory_key="last_route_intent",
        memory_value=route_intent or "unknown",
        metadata={"article_id": article_id},
    )
    upsert_long_term_memory(
        db,
        user_id=user_id,
        namespace="operator_preferences",
        memory_key="last_article_id",
        memory_value=article_id,
        metadata={},
    )
    # Historise chaque output assistant avec une clé unique (pas d'écrasement).
    unique_output_key = f"output_{session_id}_{uuid.uuid4().hex[:12]}"
    upsert_long_term_memory(
        db,
        user_id=user_id,
        namespace="ask_agent_outputs",
        memory_key=unique_output_key,
        memory_value=response,
        score=1.0,
        metadata={
            "route_intent": route_intent,
            "article_id": article_id,
            "session_id": session_id,
        },
    )

