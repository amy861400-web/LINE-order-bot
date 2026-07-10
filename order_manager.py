from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List
import re


NOISE_WORDS = {
    "謝謝",
    "謝謝你",
    "謝謝唷",
    "感謝",
    "感恩",
    "麻煩",
    "拜託",
    "收到",
    "好的",
    "OK",
    "ok",
    "已付款",
}


def clean_food_name(name: str) -> str:
    text = str(name or "").strip()

    # 移除 LINE @標記
    text = re.sub(r"@\S+", " ", text)

    # 移除網址
    text = re.sub(r"https?://\S+", " ", text, flags=re.I)

    # 移除完整算式，例如 100*2=200、$100x2=200
    text = re.sub(
        r"\$?\s*\d+\s*[*xX×]\s*\d+\s*=\s*\d+",
        " ",
        text,
    )

    # 移除「共400、總共195、合計300」
    text = re.sub(
        r"(共|總共|合計)\s*\$?\s*\d+\s*(元)?",
        " ",
        text,
    )

    # 移除價格，例如 $100、100元、100
    text = re.sub(r"\$?\s*\d+\s*(元)?", " ", text)

    # 移除數量符號，例如 *2、x2
    text = re.sub(r"[*xX×]\s*\d+", " ", text)

    # 移除常見非餐點文字
    for word in NOISE_WORDS:
        text = text.replace(word, " ")

    for word in [
        "我要",
        "我 要",
        "請問",
        "共",
        "總共",
        "合計",
    ]:
        text = text.replace(word, " ")

    text = re.sub(r"\s+", " ", text)
    text = text.strip(" ：:-＝=,，。.!！?？")

    if not text:
        return ""

    if text in NOISE_WORDS:
        return ""

    if text.isdigit():
        return ""

    # 太像純聊天或測試字串時排除
    if text.lower() in {
        "test",
        "testing",
        "測試",
        "測試版",
        "目前",
        "沒問題",
    }:
        return ""

    return text


@dataclass
class OrderManager:
    orders: "OrderedDict[str, Dict[str, Any]]" = field(
        default_factory=OrderedDict
    )
    menu: List[Dict[str, Any]] = field(default_factory=list)
    active: bool = False
    last_order_user_id: str | None = None
    last_order_user_name: str | None = None

    def reset(
        self,
        menu: List[Dict[str, Any]] | None = None,
        active: bool = True,
    ):
        """
        開始新一輪。

        現在不使用菜單辨識，因此 menu 可保持空白。
        """
        self.orders = OrderedDict()
        self.menu = menu or []
        self.active = active
        self.last_order_user_id = None
        self.last_order_user_name = None

    def stop(self):
        self.active = False

    def public_orders(self) -> Dict[str, Dict[str, int]]:
        return {
            value["name"]: dict(value.get("items", {}))
            for value in self.orders.values()
            if value.get("items")
        }

    def apply_ai_result(
        self,
        user_id: str,
        user_name: str,
        result: Dict[str, Any],
    ):
        if not self.active:
            return

        if not isinstance(result, dict):
            return

        action = str(result.get("action", "ignore")).strip().lower()

        if action == "ignore":
            return

        if action == "cancel":
            self.orders.pop(user_id, None)

            if self.last_order_user_id == user_id:
                self.last_order_user_id = None
                self.last_order_user_name = None

            return

        if action == "copy":
            self._copy_order(
                user_id=user_id,
                user_name=user_name,
                target=result.get("target"),
            )
            return

        items = self._normalize_items(result.get("items", []))

        if not items:
            return

        # 防止 AI 把整段聊天誤判成大量餐點
        if len(items) > 10:
            return

        current = Counter(
            self.orders.get(user_id, {}).get("items", {})
        )

        if action in ("set", "order", "update"):
            final = items

        elif action in ("add", "add_note"):
            final = current + items

        else:
            return

        self.orders[user_id] = {
            "name": user_name,
            "items": Counter(final),
        }

        self.last_order_user_id = user_id
        self.last_order_user_name = user_name

    def _copy_order(
        self,
        user_id: str,
        user_name: str,
        target: str | None,
    ):
        copied = None
        target_name = str(target or "").strip()

        if target_name and target_name != "last":
            for value in self.orders.values():
                if value.get("name") == target_name:
                    copied = Counter(value.get("items", {}))
                    break

        elif (
            self.last_order_user_id
            and self.last_order_user_id in self.orders
        ):
            copied = Counter(
                self.orders[self.last_order_user_id].get("items", {})
            )

        if not copied:
            return

        self.orders[user_id] = {
            "name": user_name,
            "items": copied,
        }

        self.last_order_user_id = user_id
        self.last_order_user_name = user_name

    def _normalize_items(self, raw_items: Any) -> Counter:
        """
        不再比對菜單。

        只要 Gemini 判斷為明確餐點，清理後直接寫入。
        """
        counter = Counter()

        if not isinstance(raw_items, list):
            return counter

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            name = clean_food_name(item.get("name", ""))

            if not name:
                continue

            try:
                qty = int(item.get("qty", 1) or 1)
            except (TypeError, ValueError):
                qty = 1

            if qty < 1 or qty > 50:
                continue

            counter[name] += qty

        return counter

    def summary(self) -> str:
        if not self.orders:
            return "目前沒有訂單"

        lines: List[str] = []
        total = Counter()

        for value in self.orders.values():
            items = Counter(value.get("items", {}))

            if not items:
                continue

            display_name = str(value.get("name", "")).strip()

            lines.append(f"{display_name} :")

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
