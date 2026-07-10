from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List
import hashlib
import re
from rapidfuzz import process, fuzz

NOISE_PATTERNS = [
    r"@\S+", r"https?://\S+", r"\$", r"元", r"謝謝", r"感謝", r"麻煩", r"拜託",
    r"共\s*\d+", r"總共\s*\d+", r"合計\s*\d+", r"=\s*\d+",
]


def clean_text(text: str) -> str:
    text = text or ""
    for p in NOISE_PATTERNS:
        text = re.sub(p, " ", text, flags=re.I)
    text = re.sub(r"\d+\s*[*xX×]\s*\d+", " ", text)
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"[，,。；;：:\-_=+!！?？()（）\[\]【】]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class OrderManager:
    orders: "OrderedDict[str, Dict[str, Any]]" = field(default_factory=OrderedDict)
    menu: List[Dict[str, Any]] = field(default_factory=list)
    menu_fingerprint: str = ""
    active: bool = False
    last_order_user_id: str | None = None
    last_order_user_name: str | None = None

    def reset(self, menu: List[Dict[str, Any]] | None = None, active: bool = True):
        self.orders = OrderedDict()
        self.menu = self._dedupe_menu(menu or [])
        self.menu_fingerprint = self.menu_hash(self.menu)
        self.active = active
        self.last_order_user_id = None
        self.last_order_user_name = None

    def stop(self):
        self.active = False

    def menu_hash(self, menu: List[Dict[str, Any]]) -> str:
        names = sorted({str(x.get("name", "")).strip() for x in menu if str(x.get("name", "")).strip()})
        return hashlib.sha256("|".join(names).encode("utf-8")).hexdigest()[:16] if names else ""

    def _dedupe_menu(self, menu: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out = []
        for item in menu or []:
            name = clean_text(str(item.get("name", "")))
            if not name or len(name) < 2:
                continue
            if name in seen:
                continue
            seen.add(name)
            price = item.get("price")
            try:
                price = int(price) if price not in (None, "") else None
            except Exception:
                price = None
            out.append({"name": name, "price": price})
        return out

    def menu_names(self) -> List[str]:
        return [x["name"] for x in self.menu if x.get("name")]

    def public_orders(self) -> Dict[str, Dict[str, int]]:
        return {v["name"]: dict(v.get("items", {})) for v in self.orders.values() if v.get("items")}

    def resolve_menu_item(self, raw_name: str) -> str | None:
        raw = clean_text(raw_name)
        if not raw:
            return None
        names = self.menu_names()
        if not names:
            return None
        if raw in names:
            return raw
        # substring match: 三杯雞 -> 塔香三杯雞
        candidates = [n for n in names if raw in n or n in raw]
        if candidates:
            return sorted(candidates, key=len)[0]
        match = process.extractOne(raw, names, scorer=fuzz.WRatio)
        if match and match[1] >= 78:
            return match[0]
        return None

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
            self._copy_order(user_id, user_name, result.get("target"))
            return
        raw_items = result.get("items", [])
        items = self._normalize_items(raw_items)
        if not items:
            return
        if len(items) > 6:
            return
        current = Counter(self.orders.get(user_id, {}).get("items", {}))
        if action in ("set", "order", "update"):
            final = items
        elif action in ("add", "add_note"):
            final = current + items
        else:
            return
        self.orders[user_id] = {"name": user_name, "items": Counter(final)}
        self.last_order_user_id = user_id
        self.last_order_user_name = user_name

    def _copy_order(self, user_id: str, user_name: str, target: str | None):
        copied = None
        target = (target or "").strip()
        if target and target != "last":
            for v in self.orders.values():
                if v.get("name") == target:
                    copied = Counter(v.get("items", {}))
                    break
        elif self.last_order_user_id and self.last_order_user_id in self.orders:
            copied = Counter(self.orders[self.last_order_user_id].get("items", {}))
        if copied:
            self.orders[user_id] = {"name": user_name, "items": copied}
            self.last_order_user_id = user_id
            self.last_order_user_name = user_name

    def _normalize_items(self, raw_items: Any) -> Counter:
        counter = Counter()
        if not isinstance(raw_items, list):
            return counter
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            resolved = self.resolve_menu_item(str(item.get("name", "")))
            if not resolved:
                continue
            try:
                qty = int(item.get("qty", 1) or 1)
            except Exception:
                qty = 1
            if 1 <= qty <= 20:
                counter[resolved] += qty
        return counter

    def summary(self) -> str:
        if not self.orders:
            return "目前沒有訂單"
        lines: List[str] = []
        total = Counter()
        for v in self.orders.values():
            items = Counter(v.get("items", {}))
            if not items:
                continue
            lines.append(f"{v.get('name', '')} :")
            for food, qty in items.items():
                lines.append(f"{food} {qty}")
                total[food] += qty
            lines.append("")
        if not total:
            return "目前沒有訂單"
        lines.append("----------------")
        lines.append("")
        for food, qty in total.items():
            lines.append(f"{food} {qty}")
        return "\n".join(lines).strip()
