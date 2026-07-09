from collections import Counter
from typing import Dict, Any

class OrderManager:
    def __init__(self):
        self.orders: Dict[str, Dict[str, str]] = {}
        self.menu = []
        self.active = True
        self.last_order_user_id = None
        self.last_order_user_name = None

    def reset(self, menu=None, active=True):
        self.orders = {}
        self.menu = menu or []
        self.active = active
        self.last_order_user_id = None
        self.last_order_user_name = None

    def stop(self):
        self.active = False

    def public_orders(self):
        return {v["name"]: v["order"] for v in self.orders.values() if v.get("order")}

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
            target = result.get("target") or self.last_order_user_name
            copied = None
            for v in self.orders.values():
                if v.get("name") == target:
                    copied = v.get("order")
                    break
            if copied:
                self.orders[user_id] = {"name": user_name, "order": copied}
                self.last_order_user_id = user_id
                self.last_order_user_name = user_name
            return
        if action in ("order", "update", "add_note"):
            order = (result.get("order") or "").strip()
            note = (result.get("note") or "").strip()
            existing = self.orders.get(user_id, {}).get("order", "")
            if action == "add_note" and existing:
                final = existing + ("+" + note if note and not note.startswith(("不要", "去", "少")) else ("(" + note + ")" if note else ""))
            else:
                final = order or existing
                if note:
                    final += f"({note})" if note.startswith(("不要", "去", "少")) else "+" + note
            if final:
                self.orders[user_id] = {"name": user_name, "order": final}
                self.last_order_user_id = user_id
                self.last_order_user_name = user_name

    def detail(self):
        if not self.orders:
            return "目前沒有訂單"
        lines = ["🍱 今日訂單", ""]
        for v in self.orders.values():
            lines.append(f"{v['name']}　{v['order']}")
        return "\n".join(lines)

    def summary(self):
        if not self.orders:
            return "目前沒有訂單"
        lines = ["🍱 今日訂單", ""]
        counts = Counter()
        for v in self.orders.values():
            order = v["order"]
            lines.append(f"{v['name']}　{order}")
            for item in self._split_items(order):
                counts[item] += 1
        lines += ["", "----------------", ""]
        for item, qty in counts.items():
            lines.append(f"{item}　{qty}")
        return "\n".join(lines)

    def _split_items(self, order: str):
        # 簡單切分主餐與加點；備註如「不要蔥」不列入統計
        text = order.replace("＋", "+").replace("，", "+").replace(",", "+")
        # 移除括號內備註
        import re
        text = re.sub(r"[（(].*?[)）]", "", text)
        parts = [p.strip() for p in text.split("+") if p.strip()]
        return parts or [order]
