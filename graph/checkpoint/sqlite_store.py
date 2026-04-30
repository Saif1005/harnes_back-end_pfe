from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from harness_backend.core.state import HarnessState
from harness_backend.graph.checkpoint.store import CheckpointStore


class SQLiteCheckpointStore(CheckpointStore):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save(self, state: HarnessState, node_name: str) -> None:
        run_id = state.get("run_id", "")
        created_at = state.get("updated_at", "")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO graph_checkpoints (run_id, node_name, state_json, created_at) VALUES (?, ?, ?, ?)",
                (run_id, node_name, json.dumps(state), created_at),
            )
            conn.commit()

    def load_latest(self, run_id: str) -> HarnessState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM graph_checkpoints WHERE run_id = ? ORDER BY id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def list_latest_states(self, limit: int = 200) -> list[HarnessState]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT gc.run_id, gc.state_json
                FROM graph_checkpoints gc
                INNER JOIN (
                    SELECT run_id, MAX(id) AS max_id
                    FROM graph_checkpoints
                    GROUP BY run_id
                ) latest ON gc.run_id = latest.run_id AND gc.id = latest.max_id
                ORDER BY gc.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [json.loads(state_json) for _, state_json in rows]

