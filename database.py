from __future__ import annotations
import os, sqlite3, threading
from pathlib import Path
from typing import Any

class OrderDatabase:
    def __init__(self, db_path: str | None = None):
        self.path=Path(db_path or os.getenv("DB_PATH","data/orders.db")); self.path.parent.mkdir(parents=True,exist_ok=True); self._lock=threading.RLock(); self._init_schema()
    def _connect(self):
        c=sqlite3.connect(self.path,timeout=20); c.row_factory=sqlite3.Row; c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON"); return c
    def _init_schema(self):
        with self._lock,self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS rounds(id INTEGER PRIMARY KEY AUTOINCREMENT,scope_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,closed_at TEXT);
            CREATE INDEX IF NOT EXISTS idx_rounds_scope_status ON rounds(scope_id,status,id);
            CREATE TABLE IF NOT EXISTS orders(round_id INTEGER NOT NULL,user_id TEXT NOT NULL,user_name TEXT NOT NULL,food_name TEXT NOT NULL,qty INTEGER NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(round_id,user_id,food_name),FOREIGN KEY(round_id) REFERENCES rounds(id) ON DELETE CASCADE);
            CREATE INDEX IF NOT EXISTS idx_orders_round ON orders(round_id,user_id);
            """)
    def start_round(self,scope_id):
        with self._lock,self._connect() as c:
            c.execute("UPDATE rounds SET status='closed',closed_at=CURRENT_TIMESTAMP WHERE scope_id=? AND status='open'",(scope_id,)); cur=c.execute("INSERT INTO rounds(scope_id,status) VALUES(?,'open')",(scope_id,)); return int(cur.lastrowid)
    def active_round(self,scope_id):
        with self._lock,self._connect() as c:
            r=c.execute("SELECT id FROM rounds WHERE scope_id=? AND status='open' ORDER BY id DESC LIMIT 1",(scope_id,)).fetchone(); return int(r['id']) if r else None
    def close_round(self,scope_id):
        with self._lock,self._connect() as c: c.execute("UPDATE rounds SET status='closed',closed_at=CURRENT_TIMESTAMP WHERE scope_id=? AND status='open'",(scope_id,))
    def clear_orders(self,scope_id):
        rid=self.active_round(scope_id) or self.start_round(scope_id)
        with self._lock,self._connect() as c: c.execute("DELETE FROM orders WHERE round_id=?",(rid,))
    def add_items(self,scope_id,user_id,user_name,items):
        rid=self.active_round(scope_id)
        if rid is None:return False
        with self._lock,self._connect() as c:
            for food,qty in items.items(): c.execute("""INSERT INTO orders(round_id,user_id,user_name,food_name,qty) VALUES(?,?,?,?,?) ON CONFLICT(round_id,user_id,food_name) DO UPDATE SET user_name=excluded.user_name,qty=orders.qty+excluded.qty,updated_at=CURRENT_TIMESTAMP""",(rid,user_id,user_name,food,qty))
        return True
    def set_items(self,scope_id,user_id,user_name,items):
        rid=self.active_round(scope_id)
        if rid is None:return False
        with self._lock,self._connect() as c:
            c.execute("DELETE FROM orders WHERE round_id=? AND user_id=?",(rid,user_id))
            for food,qty in items.items(): c.execute("INSERT INTO orders(round_id,user_id,user_name,food_name,qty) VALUES(?,?,?,?,?)",(rid,user_id,user_name,food,qty))
        return True
    def cancel_user(self,scope_id,user_id):
        rid=self.active_round(scope_id)
        if rid is None:return
        with self._lock,self._connect() as c:c.execute("DELETE FROM orders WHERE round_id=? AND user_id=?",(rid,user_id))
    def user_items(self,scope_id,user_id):
        rid=self.active_round(scope_id)
        if rid is None:return []
        with self._lock,self._connect() as c:return [dict(r) for r in c.execute("SELECT food_name,qty FROM orders WHERE round_id=? AND user_id=? ORDER BY food_name COLLATE NOCASE",(rid,user_id)).fetchall()]
    def all_orders(self,scope_id):
        rid=self.active_round(scope_id)
        if rid is None:return []
        with self._lock,self._connect() as c:return [dict(r) for r in c.execute("SELECT user_id,user_name,food_name,qty,updated_at FROM orders WHERE round_id=? ORDER BY user_name COLLATE NOCASE,food_name COLLATE NOCASE",(rid,)).fetchall()]
    def last_order_user_id(self,scope_id):
        rid=self.active_round(scope_id)
        if rid is None:return None
        with self._lock,self._connect() as c:
            r=c.execute("SELECT user_id FROM orders WHERE round_id=? ORDER BY updated_at DESC LIMIT 1",(rid,)).fetchone(); return str(r['user_id']) if r else None
    def find_user_id_by_name(self,scope_id,user_name):
        rid=self.active_round(scope_id)
        if rid is None:return None
        with self._lock,self._connect() as c:
            r=c.execute("SELECT user_id FROM orders WHERE round_id=? AND user_name=? ORDER BY updated_at DESC LIMIT 1",(rid,user_name)).fetchone(); return str(r['user_id']) if r else None
