from __future__ import annotations

from collections import Counter, OrderedDict
from typing import Any
import re

from database import OrderDatabase


class OrderManager:
    def __init__(self, db: OrderDatabase | None = None):
        self.db = db or OrderDatabase()
        self._last_user_by_scope: dict[str, str] = {}
        self.last_order_user_name: str | None = None
        self.menu: list[dict[str, Any]] = []

    def start_new_round(self, scope_id: str) -> None:
        self.db.start_round(scope_id)
        self._last_user_by_scope.pop(scope_id, None)
        self.last_order_user_name = None

    def is_active(self, scope_id: str) -> bool:
        return self.db.active_round(scope_id) is not None

    def stop(self, scope_id: str) -> None:
        self.db.stop_round(scope_id)

    def clear(self, scope_id: str) -> None:
        self.db.clear_orders(scope_id)
        self._last_user_by_scope.pop(scope_id, None)
        self.last_order_user_name = None

    def public_orders(self, scope_id: str) -> dict[str, dict[str, int]]:
        grouped: OrderedDict[str, dict[str, int]] = OrderedDict()
        for row in self.db.all_orders(scope_id):
            grouped.setdefault(row["user_name"], OrderedDict())
            grouped[row["user_name"]][row["food_name"]] = int(row["qty"])
        return dict(grouped)

    def apply_ai_result(
        self,
        scope_id: str,
        user_id: str,
        user_name: str,
        result: dict[str, Any],
    ) -> bool:
        if not self.is_active(scope_id) or not isinstance(result, dict):
            return False

        action = str(result.get("action", "ignore")).lower().strip()
        if action == "ignore":
            return False

        if action == "cancel":
            self.db.cancel_user(scope_id, user_id)
            return True

        if action == "copy":
            target = str(result.get("target", "last") or "last").strip()
            ok = self.db.copy_items(
                scope_id=scope_id,
                user_id=user_id,
                user_name=user_name,
                target=target,
                last_user_id=self._last_user_by_scope.get(scope_id),
            )
            if ok:
                self._last_user_by_scope[scope_id] = user_id
                self.last_order_user_name = user_name
            return ok

        items = self._normalize_items(result.get("items", []))
        if not items:
            return False

        if action in {"set", "update", "order"}:
            ok = self.db.set_items(scope_id, user_id, user_name, dict(items))
        elif action in {"add", "add_note"}:
            ok = self.db.add_items(scope_id, user_id, user_name, dict(items))
        else:
            return False

        if ok:
            self._last_user_by_scope[scope_id] = user_id
            self.last_order_user_name = user_name
        return ok

    def my_order(self, scope_id: str, user_id: str) -> str:
        items = self.db.user_items(scope_id, user_id)
        if not items:
            return "目前沒有訂單"
        return "\n".join(f"{food} {qty}" for food, qty in items.items())

    def summary(self, scope_id: str) -> str:
        rows = self.db.all_orders(scope_id)
        if not rows:
            return "目前沒有訂單"

        users: OrderedDict[str, OrderedDict[str, int]] = OrderedDict()
        total: Counter[str] = Counter()

        for row in rows:
            name = str(row["user_name"])
            food = str(row["food_name"])
            qty = int(row["qty"])
            users.setdefault(name, OrderedDict())
            users[name][food] = users[name].get(food, 0) + qty
            total[food] += qty

        lines: list[str] = []
        for name, items in users.items():
            lines.append(f"{name} :")
            for food, qty in self._grouped_items(items):
                lines.append(f"{food} {qty}")
            lines.append("")

        lines.append("----------------")
        lines.append("")
        for food, qty in self._grouped_items(total):
            lines.append(f"{food} {qty}")

        return "\n".join(lines).strip()

    @classmethod
    def _grouped_items(cls, items) -> list[tuple[str, int]]:
        """
        相同主餐的不同備註排在一起，但不合併不同備註。
        主餐群組依第一次出現順序排列，群組內主餐本體排最前面。
        """
        groups: OrderedDict[str, list[tuple[int, str, int]]] = OrderedDict()
        for index, (food, qty) in enumerate(items.items()):
            base = cls._base_food_name(food)
            groups.setdefault(base, []).append((index, food, int(qty)))

        output: list[tuple[str, int]] = []
        for base, group in groups.items():
            group.sort(key=lambda row: (0 if row[1] == base else 1, row[0]))
            output.extend((food, qty) for _, food, qty in group)
        return output

    @staticmethod
    def _base_food_name(food: str) -> str:
        """取得用於排序分組的主餐名稱，不改變實際顯示文字。"""
        value = str(food or "").strip()
        patterns = [
            r"\s+(飯半|半飯|飯少|少飯|飯多|多飯|不要飯|去飯)$",
            r"\s+(不要|不加|去掉|少|多|加)(蔥|蒜|辣|菜|醬|飯|蛋|酸菜|香菜).*$",
            r"\s+(微辣|小辣|中辣|大辣|不辣)$",
            r"\s*\((飯半|半飯|飯少|少飯|不要菜|不要辣|不辣).+?\)$",
        ]

        base = value
        for pattern in patterns:
            base = re.sub(pattern, "", base).strip()

        if base == value and " " in value:
            first, rest = value.split(" ", 1)
            if any(token in rest for token in (
                "飯半", "半飯", "飯少", "少飯", "飯多", "多飯",
                "不要", "不加", "少", "加", "辣", "去",
            )):
                base = first

        return base or value

    @staticmethod
    def _normalize_items(raw_items: Any) -> Counter[str]:
        result: Counter[str] = Counter()
        if not isinstance(raw_items, list):
            return result

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
                result[name] += qty
        return result
