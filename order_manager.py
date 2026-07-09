from __future__ import annotations

from collections import Counter, OrderedDict
from typing import Any, Dict, List
import hashlib
import json


def clean_name(name: str) -> str:
    return (name or "").strip()


class OrderManager:
    def __init__(self):
        self.orders: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self.menu: List[Dict[str, Any]] = []
        self.menu_fingerprint = ""
        self.active = True
        self.last_order_user_id: str | None = None
        self.last_order_user_name: str | None = None

    def menu_hash(self, menu: List[Dict[str, Any]]) -> str:
        names = []
        for item in menu or []:
            n = str(item.get("name", "")).strip()
            if n:
                names.append(n)
        text = "|".join(sorted(set(names)))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""

    def reset_if_new_menu(self, menu: List[Dict[str, Any]]) -> bool:
        new_hash = self.menu_hash(menu)
        if not new_hash:
            return False
        if new_hash == self.menu_fingerprint:
            return False
        self.orders = OrderedDict()
        self.menu = menu or []
        self.menu_fingerprint = new_hash
        self.active = True
        self.last_order_user_id = None
        self.last_order_user_name = None
        return True

    def reset(self, menu=None, active=True):
        self.orders = OrderedDict()
        self.menu = menu or []
        self.menu_fingerprint = self.menu_hash(self.menu)
        self.active = active
        self.last_order_user_id = None
        self.last_order_user_name = None

    def stop(self):
        self.active = False

    def public_orders(self) -> Dict[str, Dict[str, int]]:
        return {v["name"]: dict(v.get("items", {})) for v in self.orders.values() if v.get("items")}

    def apply_ai_result(self, user_id: str, user_name: str, result: Dict[str, Any]):
        if not isinstance(result, dict):
            return

        action = result.get("action", "ignore")
        if action == "ignore":
            return

        if action == "cancel":
            self.orders.pop(user_id, None)
            return

        if action == "copy":
            target = (result.get("target") or "").strip()
            copied = None
            if target and target != "last":
                for v in self.orders.values():
                    if v.get("name") == target:
                        copied = Counter(v.get("items", {}))
                        break
            else:
                if self.last_order_user_id and self.last_order_user_id in self.orders:
                    copied = Counter(self.orders[self.last_order_user_id].get("items", {}))

            if copied:
                self.orders[user_id] = {"name": user_name, "items": copied}
                self.last_order_user_id = user_id
                self.last_order_user_name = user_name
            return

        items = self._normalize_items(result.get("items", []))
        if not items:
            return

        current = Counter(self.orders.get(user_id, {}).get("items", {}))

        if action in ("set", "order", "update"):
            # 若同一個人只重複送同一道餐，視為加一份；多項訂單則覆蓋成最新完整訂單。
            if len(items) == 1 and len(current) == 1:
                only_new = next(iter(items))
                only_old = next(iter(current))
                if only_new == only_old:
                    current[only_new] += items[only_new]
                    final = current
                else:
                    final = items
            else:
                final = items
        elif action in ("add", "add_note"):
            final = current + items
        else:
            return

        self.orders[user_id] = {"name": user_name, "items": Counter(final)}
        self.last_order_user_id = user_id
        self.last_order_user_name = user_name

    def summary(self) -> str:
        if not self.orders:
            return "目前沒有訂單"

        lines: List[str] = []
        total = Counter()

        for v in self.orders.values():
            name = v.get("name", "")
            items = Counter(v.get("items", {}))
            if not items:
                continue
            lines.append(f"{name} :")
            for food, qty in items.items():
                lines.append(f"{food} {qty}")
                total[food] += qty
            lines.append("")

        lines.append("----------------")
        lines.append("")
        for food, qty in total.items():
            lines.append(f"{food} {qty}")

        return "\n".join(lines).strip()

    def _normalize_items(self, raw_items: Any) -> Counter:
        counter = Counter()
        if not isinstance(raw_items, list):
            return counter

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            name = clean_name(str(item.get("name", "")))
            if not name:
                continue
            # 移除價格、金額、謝謝等不該進統計的字樣
            for token in ["謝謝", "感謝", "共", "總共", "合計"]:
                name = name.replace(token, "")
            name = name.replace("$", "").strip()
            if not name or name.isdigit():
                continue
            try:
                qty = int(item.get("qty", 1) or 1)
            except Exception:
                qty = 1
            if qty <= 0:
                continue
            counter[name] += qty
        return counter
