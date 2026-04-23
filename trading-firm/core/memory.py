"""
SQLite-backed agent memory store.
Provides short-term key/value memory with TTL, market outcome tracking,
and agent accuracy computation.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from core.logger import get_logger

logger = get_logger("memory")

_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


class Memory:
    """Thread-safe SQLite memory store for all agents."""

    def __init__(self, db_path: str = "logs/memory.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = sqlite3.connect(
            db_path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES
        )
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id    TEXT    NOT NULL,
                    key         TEXT    NOT NULL,
                    value_json  TEXT    NOT NULL,
                    created_at  TEXT    NOT NULL,
                    expires_at  TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_agent_key
                    ON memories(agent_id, key);

                CREATE TABLE IF NOT EXISTS market_outcomes (
                    market_id   TEXT PRIMARY KEY,
                    question    TEXT NOT NULL,
                    resolved_as TEXT NOT NULL,
                    resolved_at TEXT NOT NULL,
                    notes       TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_accuracy (
                    agent_id    TEXT PRIMARY KEY,
                    total       INTEGER NOT NULL DEFAULT 0,
                    correct     INTEGER NOT NULL DEFAULT 0,
                    computed_at TEXT    NOT NULL
                );
            """)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Core memory operations
    # ------------------------------------------------------------------

    def remember(
        self,
        agent_id: str,
        key: str,
        value: Any,
        ttl_hours: Optional[float] = None,
    ) -> None:
        """Store or update a key/value pair for an agent."""
        value_json = json.dumps(value, default=str)
        now_iso = _NOW().isoformat()
        expires_iso: Optional[str] = None
        if ttl_hours is not None:
            expires_iso = (_NOW() + timedelta(hours=ttl_hours)).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO memories (agent_id, key, value_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, key) DO UPDATE SET
                    value_json = excluded.value_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (agent_id, key, value_json, now_iso, expires_iso),
            )
            self._conn.commit()

    def recall(self, agent_id: str, key: str) -> Optional[Any]:
        """Retrieve a value for (agent_id, key), or None if not found / expired."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value_json, expires_at FROM memories WHERE agent_id=? AND key=?",
                (agent_id, key),
            ).fetchone()
        if row is None:
            return None
        if row["expires_at"] and _NOW() > datetime.fromisoformat(row["expires_at"]):
            return None
        return json.loads(row["value_json"])

    def recall_recent(self, agent_id: str, limit: int = 20) -> list[tuple[str, Any]]:
        """Return up to `limit` recent non-expired memories for an agent."""
        now_iso = _NOW().isoformat()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT key, value_json FROM memories
                WHERE agent_id=?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY created_at DESC LIMIT ?
                """,
                (agent_id, now_iso, limit),
            ).fetchall()
        return [(r["key"], json.loads(r["value_json"])) for r in rows]

    def search_memory(self, agent_id: str, query: str) -> list[tuple[str, Any]]:
        """LIKE search over keys for an agent."""
        pattern = f"%{query}%"
        now_iso = _NOW().isoformat()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT key, value_json FROM memories
                WHERE agent_id=? AND key LIKE ?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY created_at DESC LIMIT 50
                """,
                (agent_id, pattern, now_iso),
            ).fetchall()
        return [(r["key"], json.loads(r["value_json"])) for r in rows]

    def forget_expired(self) -> int:
        """Delete all expired memory rows. Returns count deleted."""
        now_iso = _NOW().isoformat()
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now_iso,),
            )
            self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Market outcomes
    # ------------------------------------------------------------------

    def record_market_outcome(
        self,
        market_id: str,
        question: str,
        resolved_as: str,
        notes: str = "",
    ) -> None:
        """Record the resolution of a market."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO market_outcomes (market_id, question, resolved_as, resolved_at, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(market_id) DO UPDATE SET
                    resolved_as = excluded.resolved_as,
                    resolved_at = excluded.resolved_at,
                    notes       = excluded.notes
                """,
                (market_id, question, resolved_as, _NOW().isoformat(), notes),
            )
            self._conn.commit()

    def get_market_outcome(self, market_id: str) -> Optional[dict]:
        """Return outcome dict for a market or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM market_outcomes WHERE market_id=?", (market_id,)
            ).fetchone()
        return dict(row) if row else None

    def search_market_outcomes(self, query: str, limit: int = 20) -> list[dict]:
        """Search market questions by LIKE query."""
        pattern = f"%{query}%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM market_outcomes WHERE question LIKE ? LIMIT ?",
                (pattern, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Agent accuracy
    # ------------------------------------------------------------------

    def get_agent_accuracy(self, agent_id: str) -> float:
        """Return accuracy [0.0, 1.0] for an agent (0.5 if no data)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT total, correct FROM agent_accuracy WHERE agent_id=?",
                (agent_id,),
            ).fetchone()
        if row is None or row["total"] == 0:
            return 0.5  # neutral prior
        return row["correct"] / row["total"]

    def update_agent_accuracy(self, agent_id: str, was_correct: bool) -> None:
        """Increment total (and correct if applicable) for an agent."""
        with self._lock:
            existing = self._conn.execute(
                "SELECT total, correct FROM agent_accuracy WHERE agent_id=?",
                (agent_id,),
            ).fetchone()
            if existing:
                total = existing["total"] + 1
                correct = existing["correct"] + (1 if was_correct else 0)
                self._conn.execute(
                    "UPDATE agent_accuracy SET total=?, correct=?, computed_at=? WHERE agent_id=?",
                    (total, correct, _NOW().isoformat(), agent_id),
                )
            else:
                self._conn.execute(
                    "INSERT INTO agent_accuracy (agent_id, total, correct, computed_at) VALUES (?,?,?,?)",
                    (agent_id, 1, 1 if was_correct else 0, _NOW().isoformat()),
                )
            self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()
