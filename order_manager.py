from __future__ import annotations

from collections import Counter, OrderedDict
from difflib import SequenceMatcher
from typing import Any, Dict, List
import hashlib
import re


def clean_text(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"@[\S]+", " ", t)
    t = re.sub(r"https?://\S+|www\.\S+", " ", t, flags=re.I)
    t = re.sub(r"\$?\s*\d+\s*[*xX×]\s*\d+\s*=\s*\d+", " ", t)
    t = re.sub(r"=\s*\d+", " ", t)
    t = re.sub(r"\$?\s*\d+\s*(元)?", " ", t)
    for token in ["謝謝", "感謝", "感恩", "麻煩", "請", "共", "總共", "合計", "OK", "ok", "收到"]:
        t = t.replace(token, " ")
    t = re.sub(r"\s+", " ", t)
    return t.strip(" ：:，,。.-")


def normalize_for_match(text: str) -> str:
    t = clean_text(text)
    t = re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)
    return t.lower()


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
        clean_menu = self._clean_menu(menu)
        new_hash = self.menu_hash(clean_menu)

        if not new_hash:
            return False

        if new_hash == self.menu_fingerprint:
            return False

        self.orders = OrderedDict()
        self.menu = clean_menu
        self.menu_fingerprint = new_hash
        self.active = True
        self.last_order_user_id = None
        self.last_order_user_name = None
        return True

    def reset(self, menu=None, active=True):
        self.orders = OrderedDict()
        self.menu = self._clean_menu(menu or [])
        self.menu_fingerprint = self.menu_hash(self.menu)
        self.active = active
        self.last_order_user_id = None
        self.last_order_user_name = None

    def stop(self):
        self.active = False

    def public_orders(self) -> Dict[str, Dict[str, int]]:
        return {
            v["name"]: dict(v.get("items", {}))
            for v in self.orders.values()
            if v.get("items")
        }

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
            self._copy_order(user_id=user_id, user_name=user_name, target=result.get("target"))
            return

        items = self._normalize_items(result.get("items", []))

        # AI 異常保護：一次超過 5 個品項，通常是把菜單整份當成訂單。
        if len(items) > 5:
            return

        if not items:
            return

        current = Counter(self.orders.get(user_id, {}).get("items", {}))

        if action in ("set", "order", "update"):
            # 「改」或完整訂單 → 覆蓋
            final = items

            # 若同一個人連續送同一道餐，視為累加
            if len(items) == 1 and len(current) == 1:
                only_new = next(iter(items))
                only_old = next(iter(current))
                if only_new == only_old:
                    current[only_new] += items[only_new]
                    final = current

        elif action in ("add", "add_note"):
            final = current + items

        else:
            return

        self.orders[user_id] = {"name": user_name, "items": Counter(final)}
        self.last_order_user_id = user_id
        self.last_order_user_name = user_name

    def _copy_order(self, user_id: str, user_name: str, target: str | None):
        target = (target or "").strip()
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

    def _clean_menu(self, raw_menu: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        seen = set()

        for item in raw_menu or []:
            if not isinstance(item, dict):
                continue

            name = clean_text(str(item.get("name", "")))

            if not name:
                continue

            # 菜名不能是明顯非餐點內容
            if self._looks_like_noise(name):
                continue

            key = normalize_for_match(name)
            if not key or key in seen:
                continue

            seen.add(key)
            result.append({"name": name, "price": item.get("price")})

        return result

    def _normalize_items(self, raw_items: Any) -> Counter:
        counter = Counter()

        if not isinstance(raw_items, list):
            return counter

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            raw_name = clean_text(str(item.get("name", "")))
            if not raw_name or self._looks_like_noise(raw_name):
                continue

            menu_name = self._match_menu_name(raw_name)

            # 最重要防呆：不是目前菜單品項 → 不加入訂單
            if not menu_name:
                continue

            try:
                qty = int(item.get("qty", 1) or 1)
            except Exception:
                qty = 1

            if qty <= 0 or qty > 20:
                continue

            counter[menu_name] += qty

        return counter

    def _match_menu_name(self, name: str) -> str | None:
        if not self.menu:
            return None

        target = normalize_for_match(name)
        if not target:
            return None

        menu_names = [str(x.get("name", "")).strip() for x in self.menu if str(x.get("name", "")).strip()]
        menu_norm = {normalize_for_match(n): n for n in menu_names}

        # 完全一致
        if target in menu_norm:
            return menu_norm[target]

        # 使用者輸入是菜名的一部分，例如「三杯雞」→「塔香三杯雞」
        candidates = []
        for norm, original in menu_norm.items():
            if target and target in norm:
                candidates.append((len(norm), original))
            elif norm and norm in target:
                candidates.append((len(norm), original))

        if candidates:
            candidates.sort()
            return candidates[0][1]

        # 模糊比對
        best_name = None
        best_score = 0.0
        for norm, original in menu_norm.items():
            score = SequenceMatcher(None, target, norm).ratio()
            if score > best_score:
                best_score = score
                best_name = original

        if best_score >= 0.72:
            return best_name

        return None

    def _looks_like_noise(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return True

        low = t.lower()

        noise_words = [
            "謝謝", "感謝", "感恩", "ok", "收到", "共", "總共", "合計",
            "測試", "test", "午安", "早安", "晚安", "哈哈", "已付款",
            "付款", "不用", "不要了", "網址", "電話", "地址",
        ]

        if any(w in low for w in noise_words):
            return True

        if re.fullmatch(r"\d+", t):
            return True

        if re.fullmatch(r"[@#\W_]+", t):
            return True

        if re.search(r"https?://|www\.", t, re.I):
            return True

        return False
