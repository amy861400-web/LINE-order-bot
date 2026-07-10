from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, OrderedDict
from contextlib import contextmanager
from typing import Any, Dict, Iterator


class OrderDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        directory = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(directory, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS rounds (
                    scope TEXT PRIMARY KEY,
                    active INTEGER NOT NULL DEFAULT 0,
                    round_no INTEGER NOT NULL DEFAULT 0,
                    last_user_id TEXT,
                    last_user_name TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS orders (
                    scope TEXT NOT NULL,
                    round_no INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (scope, round_no, user_id)
                );
                """
            )

    def _ensure_scope(self, scope: str) -> sqlite3.Row:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO rounds(scope, active, round_no) VALUES (?, 0, 0)",
                (scope,),
            )
            return conn.execute("SELECT * FROM rounds WHERE scope = ?", (scope,)).fetchone()

    def start_new_round(self, scope: str) -> None:
        row = self._ensure_scope(scope)
        new_round = int(row["round_no"]) + 1
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE rounds
                SET active = 1, round_no = ?, last_user_id = NULL, last_user_name = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE scope = ?
                """,
                (new_round, scope),
            )

    def stop_round(self, scope: str) -> None:
        self._ensure_scope(scope)
        with self._connect() as conn:
            conn.execute(
                "UPDATE rounds SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE scope = ?",
                (scope,),
            )

    def is_active(self, scope: str) -> bool:
        return bool(self._ensure_scope(scope)["active"])

    def _round_no(self, scope: str) -> int:
        return int(self._ensure_scope(scope)["round_no"])

    def public_orders(self, scope: str) -> Dict[str, Dict[str, int]]:
        round_no = self._round_no(scope)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_name, items_json FROM orders WHERE scope = ? AND round_no = ? ORDER BY updated_at, rowid",
                (scope, round_no),
            ).fetchall()
        result: Dict[str, Dict[str, int]] = OrderedDict()
        for row in rows:
            result[row["user_name"]] = dict(json.loads(row["items_json"]))
        return result

    def last_order_user_name(self, scope: str) -> str | None:
        return self._ensure_scope(scope)["last_user_name"]

    def _get_user_items(self, scope: str, round_no: int, user_id: str) -> Counter:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT items_json FROM orders WHERE scope = ? AND round_no = ? AND user_id = ?",
                (scope, round_no, user_id),
            ).fetchone()
        return Counter(json.loads(row["items_json"])) if row else Counter()

    def _save_user_items(
        self,
        scope: str,
        round_no: int,
        user_id: str,
        user_name: str,
        items: Counter,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders(scope, round_no, user_id, user_name, items_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scope, round_no, user_id) DO UPDATE SET
                    user_name = excluded.user_name,
                    items_json = excluded.items_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (scope, round_no, user_id, user_name, json.dumps(dict(items), ensure_ascii=False)),
            )
            conn.execute(
                """
                UPDATE rounds SET last_user_id = ?, last_user_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE scope = ?
                """,
                (user_id, user_name, scope),
            )

    def apply_ai_result(
        self,
        scope: str,
        user_id: str,
        user_name: str,
        result: Dict[str, Any],
    ) -> None:
        if not self.is_active(scope) or not isinstance(result, dict):
            return
        action = str(result.get("action", "ignore")).lower()
        round_no = self._round_no(scope)

        if action == "ignore":
            return
        if action == "cancel":
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM orders WHERE scope = ? AND round_no = ? AND user_id = ?",
                    (scope, round_no, user_id),
                )
            return
        if action == "copy":
            self._copy_order(scope, round_no, user_id, user_name, str(result.get("target", "last")))
            return

        items = self._normalize_items(result.get("items", []))
        if not items or len(items) > 12:
            return
        current = self._get_user_items(scope, round_no, user_id)
        if action == "set":
            final = items
        elif action == "add":
            final = current + items
        else:
            return
        self._save_user_items(scope, round_no, user_id, user_name, final)

    def _copy_order(self, scope: str, round_no: int, user_id: str, user_name: str, target: str) -> None:
        with self._connect() as conn:
            if target and target != "last":
                row = conn.execute(
                    "SELECT items_json FROM orders WHERE scope = ? AND round_no = ? AND user_name = ? ORDER BY updated_at DESC LIMIT 1",
                    (scope, round_no, target),
                ).fetchone()
            else:
                last_user_id = self._ensure_scope(scope)["last_user_id"]
                row = conn.execute(
                    "SELECT items_json FROM orders WHERE scope = ? AND round_no = ? AND user_id = ?",
                    (scope, round_no, last_user_id),
                ).fetchone() if last_user_id else None
        if row:
            self._save_user_items(scope, round_no, user_id, user_name, Counter(json.loads(row["items_json"])))

    def _normalize_items(self, raw_items: Any) -> Counter:
        counter = Counter()
        if not isinstance(raw_items, list):
            return counter
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            try:
                qty = int(item.get("qty", 1) or 1)
            except (TypeError, ValueError):
                qty = 1
            if 1 <= qty <= 50:
                counter[name] += qty
        return counter

    def summary(self, scope: str) -> str:
        orders = self.public_orders(scope)
        if not orders:
            return "目前沒有訂單"
        lines = []
        total = Counter()
        for name, items in orders.items():
            lines.append(f"{name} :")
            for food, qty in items.items():
                lines.append(f"{food} {qty}")
                total[food] += qty
            lines.append("")
        lines.extend(["----------------", ""])
        for food, qty in total.items():
            lines.append(f"{food} {qty}")
        return "\n".join(lines).strip()

    def user_summary(self, scope: str, user_id: str, display_name: str) -> str:
        round_no = self._round_no(scope)
        items = self._get_user_items(scope, round_no, user_id)
        if not items:
            return "目前沒有訂單"
        lines = [f"{display_name} :"]
        lines.extend(f"{food} {qty}" for food, qty in items.items())
        return "\n".join(lines)
