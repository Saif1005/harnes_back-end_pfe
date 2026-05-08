from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_backend.config.settings import SETTINGS


def _connect() -> sqlite3.Connection:
    db_path = Path(SETTINGS.runtime_db_path)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        fallback = Path("/tmp/harness/runtime.sqlite")
        fallback.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.runtime_db_path = str(fallback)
        db_path = fallback
    return sqlite3.connect(str(db_path))


def init_runtime_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                route TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                ok INTEGER NOT NULL,
                model TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoke_runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                query TEXT NOT NULL,
                route TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reasoning_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'react_step',
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reasoning_memory_session ON reasoning_memory(session_id)"
        )
        conn.commit()


def persist_invoke_run(
    run_id: str,
    session_id: str,
    user_id: str,
    query: str,
    route: str,
    status: str,
    message: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO invoke_runs (
                run_id, session_id, user_id, query, route, status, message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                user_id,
                query,
                route,
                status,
                message,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def persist_tool_run(
    run_id: str,
    session_id: str,
    user_id: str,
    route: str,
    tool_name: str,
    ok: bool,
    model: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO tool_runs (
                run_id, session_id, user_id, route, tool_name, ok, model,
                payload_json, result_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                user_id,
                route,
                tool_name,
                1 if ok else 0,
                model,
                json.dumps(payload),
                json.dumps(result),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def fetch_recent_tool_runs(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT run_id, session_id, user_id, route, tool_name, ok, model, payload_json, result_json, created_at
            FROM tool_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "run_id": row[0],
                "session_id": row[1],
                "user_id": row[2],
                "route": row[3],
                "tool_name": row[4],
                "ok": bool(row[5]),
                "model": row[6],
                "payload": json.loads(row[7]),
                "result": json.loads(row[8]),
                "created_at": row[9],
            }
        )
    return out


def append_reasoning_memory(
    session_id: str,
    run_id: str,
    user_id: str,
    kind: str,
    payload: dict[str, Any],
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO reasoning_memory(session_id, run_id, user_id, kind, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                run_id,
                user_id,
                kind,
                json.dumps(payload, ensure_ascii=True, default=str),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def fetch_reasoning_memory(session_id: str, limit: int = 80) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, run_id, user_id, kind, payload_json, created_at
            FROM reasoning_memory
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, max(1, int(limit))),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row[0],
                "run_id": row[1],
                "user_id": row[2],
                "kind": row[3],
                "payload": json.loads(row[4]),
                "created_at": row[5],
            }
        )
    return list(reversed(out))


def fetch_runtime_metrics() -> dict[str, Any]:
    with _connect() as conn:
        invokes = conn.execute("SELECT COUNT(*) FROM invoke_runs").fetchone()[0]
        tools = conn.execute("SELECT COUNT(*) FROM tool_runs").fetchone()[0]
        by_tool_rows = conn.execute(
            "SELECT tool_name, COUNT(*) FROM tool_runs GROUP BY tool_name ORDER BY COUNT(*) DESC"
        ).fetchall()
        recent_invokes = conn.execute(
            """
            SELECT run_id, route, status, created_at
            FROM invoke_runs
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()
    return {
        "invoke_count": int(invokes),
        "tool_run_count": int(tools),
        "tool_usage": [{"tool_name": r[0], "count": int(r[1])} for r in by_tool_rows],
        "recent_invokes": [
            {"run_id": r[0], "route": r[1], "status": r[2], "created_at": r[3]}
            for r in recent_invokes
        ],
    }

