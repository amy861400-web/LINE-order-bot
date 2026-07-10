from __future__ import annotations

import os
import sqlite3
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any


class OrderDatabase:
    def __init__(self, db_path: str | None = None):
        path = db_path or os.getenv("DB_PATH", "data/orders.db")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS orders (
                    round_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    food_name TEXT NOT NULL,
                    qty INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (round_id, user_id, food_name),
                    FOREIGN KEY (round_id) REFERENCES rounds(id) ON DELETE CASCADE
                );
                """
            )

    def start_round(self, scope_id: str) -> int:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE rounds SET active=0 WHERE scope_id=? AND active=1",
                (scope_id,),
            )
            cur = conn.execute(
                "INSERT INTO rounds(scope_id, active) VALUES (?, 1)",
                (scope_id,),
            )
            return int(cur.lastrowid)

    def active_round(self, scope_id: str) -> int | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM rounds WHERE scope_id=? AND active=1 ORDER BY id DESC LIMIT 1",
                (scope_id,),
            ).fetchone()
            return int(row["id"]) if row else None

    def stop_round(self, scope_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE rounds SET active=0 WHERE scope_id=? AND active=1",
                (scope_id,),
            )

    def clear_orders(self, scope_id: str) -> None:
        round_id = self.active_round(scope_id)
        if round_id is None:
            self.start_round(scope_id)
            return
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM orders WHERE round_id=?", (round_id,))

    def add_items(
        self,
        scope_id: str,
        user_id: str,
        user_name: str,
        items: dict[str, int],
    ) -> bool:
        round_id = self.active_round(scope_id)
        if round_id is None:
            return False

        with self._lock, self._connect() as conn:
            for food, qty in items.items():
                conn.execute(
                    """
                    INSERT INTO orders(round_id, user_id, user_name, food_name, qty)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(round_id, user_id, food_name)
                    DO UPDATE SET
                        user_name=excluded.user_name,
                        qty=orders.qty + excluded.qty,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (round_id, user_id, user_name, food, qty),
                )
        return True

    def set_items(
        self,
        scope_id: str,
        user_id: str,
        user_name: str,
        items: dict[str, int],
    ) -> bool:
        round_id = self.active_round(scope_id)
        if round_id is None:
            return False

        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM orders WHERE round_id=? AND user_id=?",
                (round_id, user_id),
            )
            for food, qty in items.items():
                conn.execute(
                    """
                    INSERT INTO orders(round_id, user_id, user_name, food_name, qty)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (round_id, user_id, user_name, food, qty),
                )
        return True

    def cancel_user(self, scope_id: str, user_id: str) -> None:
        round_id = self.active_round(scope_id)
        if round_id is None:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM orders WHERE round_id=? AND user_id=?",
                (round_id, user_id),
            )

    def user_items(self, scope_id: str, user_id: str) -> OrderedDict[str, int]:
        round_id = self.active_round(scope_id)
        if round_id is None:
            return OrderedDict()

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT food_name, qty
                FROM orders
                WHERE round_id=? AND user_id=?
                ORDER BY rowid
                """,
                (round_id, user_id),
            ).fetchall()
            return OrderedDict((row["food_name"], int(row["qty"])) for row in rows)

    def all_orders(self, scope_id: str) -> list[dict[str, Any]]:
        round_id = self.active_round(scope_id)
        if round_id is None:
            return []

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, user_name, food_name, qty
                FROM orders
                WHERE round_id=?
                ORDER BY rowid
                """,
                (round_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def copy_items(
        self,
        scope_id: str,
        user_id: str,
        user_name: str,
        target: str,
        last_user_id: str | None,
    ) -> bool:
        round_id = self.active_round(scope_id)
        if round_id is None:
            return False

        source_user_id: str | None = None
        if target == "last":
            source_user_id = last_user_id
        else:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT user_id
                    FROM orders
                    WHERE round_id=? AND user_name=?
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (round_id, target),
                ).fetchone()
                if row:
                    source_user_id = str(row["user_id"])

        if not source_user_id:
            return False

        copied = self.user_items(scope_id, source_user_id)
        if not copied:
            return False
        return self.set_items(scope_id, user_id, user_name, dict(copied))
