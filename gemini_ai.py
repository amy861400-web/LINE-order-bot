from __future__ import annotations

import json
import os
import re
from typing import Any

import requests


TOTAL_RE = re.compile(r"^\s*(共|總共|合計|小計)\s*[$＄]?\s*\d+\s*(元)?\s*(謝謝|感謝)?\s*$", re.I)
URL_RE = re.compile(r"https?://\S+", re.I)
MENTION_RE = re.compile(r"@\S+")
EMOJI_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)

NOISE_EXACT = {
    "謝謝", "謝謝唷", "謝謝你", "感謝", "感恩", "麻煩", "拜託",
    "ok", "收到", "好", "好的", "午安", "早安", "晚安",
    "哈哈", "哈哈哈", "已付款", "付款了", "不用", "不用了",
    "測試", "測試版", "test", "testing", "目前", "沒問題",
}

FOOD_HINTS = (
    "飯", "麵", "粥", "湯", "鍋", "排", "雞", "鴨", "鵝", "魚", "蝦",
    "肉", "蛋", "餃", "包", "堡", "吐司", "三明治", "沙拉", "飲", "茶",
    "咖啡", "奶", "豆漿", "薯", "捲", "羹", "燴", "便當", "披薩",
)


class GeminiOrderAI:
    """先以本機規則解析，只有模糊訊息才呼叫 Gemini。"""

    def __init__(self, api_key: str | None):
        self.api_key = (api_key or "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    def parse_chat(
        self,
        message: str,
        user_name: str,
        menu=None,
        current_orders=None,
        last_order_user: str | None = None,
    ) -> dict[str, Any]:
        original = (message or "").strip()
        text = self._remove_mentions(original)

        if self._quick_ignore(text):
            return {"action": "ignore"}

        command = self._detect_command(text)
        if command:
            return command

        action = "add"
        working = text

        if re.match(r"^\s*(改成|換成)", working):
            working = re.sub(r"^\s*(改成|換成)", "", working, count=1).strip()
            action = "set"
        elif re.match(r"^\s*(改|換)", working):
            working = re.sub(r"^\s*(改|換)", "", working, count=1).strip()
            action = "set"
        elif re.match(r"^\s*(再加|加|\+)", working):
            working = re.sub(r"^\s*(再加|加|\+)", "", working, count=1).strip()
            action = "add"

        local_items = self._extract_items(working)
        if local_items:
            return {"action": action, "items": local_items}

        # 本機規則無法明確判斷時，才交給 Gemini。
        if self.api_key:
            result = self._ask_gemini(
                message=text,
                user_name=user_name,
                current_orders=current_orders or {},
                last_order_user=last_order_user,
            )
            if result:
                return result

        return {"action": "ignore"}

    def _detect_command(self, text: str) -> dict[str, Any] | None:
        compact = re.sub(r"\s+", "", text)

        if compact in {"取消", "取消我的", "不要了", "不用了", "取消訂單"}:
            return {"action": "cancel"}

        if "一樣" in compact:
            target = compact
            for token in ("我要", "我也要", "跟", "和", "一樣", "同樣"):
                target = target.replace(token, "")
            target = target.strip() or "last"
            if target in {"上一個", "上一位", "前一個", "前一位"}:
                target = "last"
            return {"action": "copy", "target": target}

        return None

    def _extract_items(self, text: str) -> list[dict[str, Any]]:
        parts = re.split(
            r"(?:[\n,，、；;]+|\s*[+＋&＆]\s*|\s+(?:和|跟)\s+)",
            text,
        )
        items: list[dict[str, Any]] = []

        for raw in parts:
            line = raw.strip()
            if not line or self._quick_ignore(line) or TOTAL_RE.fullmatch(line):
                continue

            qty = 1

            # 先抓數量：105x2=210、*2、×3、2份。
            qty_match = re.search(r"(?:[*xX×]\s*(\d+)|(\d+)\s*份)", line)
            if qty_match:
                qty = int(qty_match.group(1) or qty_match.group(2))
            else:
                chinese_qty = re.search(r"([兩二三四五六七八九十])\s*份", line)
                if chinese_qty:
                    qty = self._chinese_number(chinese_qty.group(1))

            # 移除總價算式與單價。
            line = re.sub(r"[$＄]?\s*\d+\s*[*xX×]\s*\d+\s*=\s*\d+", " ", line)
            line = re.sub(r"[$＄]?\s*\d+\s*(元)?", " ", line)
            line = re.sub(r"[*xX×]\s*\d+", " ", line)
            line = re.sub(r"[兩二三四五六七八九十]\s*份", " ", line)

            for word in (
                "我要", "我想要", "來一個", "來一份", "麻煩", "請問",
                "謝謝", "感謝", "感恩", "拜託", "ok", "OK",
            ):
                line = line.replace(word, " ")

            name = self._clean_name(line)
            if not name:
                continue

            if self._looks_like_food(name):
                items.append({"name": name, "qty": max(1, min(qty, 50))})

        return self._merge_items(items)

    def _looks_like_food(self, text: str) -> bool:
        lowered = text.lower()
        if lowered in NOISE_EXACT:
            return False
        if len(text) < 2 or URL_RE.search(text):
            return False
        if any(hint in text for hint in FOOD_HINTS):
            return True
        # 「招牌飯」以外也可能是簡短餐名；有中文且不是常見聊天句就保留。
        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z]{2,12}", text):
            chat_words = ("開會", "今天", "明天", "下午", "上午", "請假", "測試", "付款", "收到")
            return not any(word in text for word in chat_words)
        return False

    def _ask_gemini(
        self,
        message: str,
        user_name: str,
        current_orders: dict[str, Any],
        last_order_user: str | None,
    ) -> dict[str, Any] | None:
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        prompt = f"""
你是台灣公司 LINE 群組的訂餐文字解析器。
只輸出一個 JSON 物件，不要 Markdown、不要解釋。

訂餐人固定是發言者「{user_name}」，@提及的人不是訂餐人。
不要依賴菜單，也不要處理圖片。

允許格式：
{{"action":"ignore"}}
{{"action":"add","items":[{{"name":"餐點","qty":1}}]}}
{{"action":"set","items":[{{"name":"餐點","qty":1}}]}}
{{"action":"cancel"}}
{{"action":"copy","target":"last"}}
{{"action":"copy","target":"對方顯示名稱"}}

規則：
- 一般點餐一律 action=add，保留此人先前訂單並累加。
- 只有明確出現「改、換、改成、換成」才 action=set。
- 「取消、不要了」是 cancel。
- 「一樣、跟某人一樣」是 copy。
- 去掉價格、總價、等號、共多少元、謝謝、emoji、網址、電話、地址。
- 日常聊天、測試版、收到、OK、已付款都 ignore。
- 多行、逗號、頓號、分號，或「+、＋、&、＆」可拆成多個餐點。
- 例如「炒麵小+隔間肉湯=100謝謝」要拆成炒麵小、隔間肉湯。
- 例如「炒麵 大 +荷包蛋」要拆成炒麵 大、荷包蛋。
- 數量可辨識 x2、*2、×2、2份。

目前訂單：{json.dumps(current_orders, ensure_ascii=False)}
上一位點餐者：{last_order_user}
訊息：{message}
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }

        try:
            response = requests.post(
                endpoint,
                params={"key": self.api_key},
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw)
            return self._sanitize_ai_result(parsed)
        except Exception as exc:
            print("Gemini parse error:", repr(exc))
            return None

    def _sanitize_ai_result(self, data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None

        action = str(data.get("action", "ignore")).lower().strip()
        if action in {"ignore", "cancel"}:
            return {"action": action}
        if action == "copy":
            target = str(data.get("target", "last") or "last").strip()
            return {"action": "copy", "target": target}
        if action not in {"add", "set"}:
            return {"action": "ignore"}

        clean_items: list[dict[str, Any]] = []
        for item in data.get("items", []):
            if not isinstance(item, dict):
                continue
            name = self._clean_name(str(item.get("name", "")))
            if not name or not self._looks_like_food(name):
                continue
            try:
                qty = int(item.get("qty", 1) or 1)
            except (TypeError, ValueError):
                qty = 1
            if 1 <= qty <= 50:
                clean_items.append({"name": name, "qty": qty})

        if not clean_items:
            return {"action": "ignore"}
        return {"action": action, "items": self._merge_items(clean_items)}

    def _quick_ignore(self, text: str) -> bool:
        value = (text or "").strip()
        if not value:
            return True
        if value.lower() in NOISE_EXACT:
            return True
        if TOTAL_RE.fullmatch(value):
            return True
        if URL_RE.fullmatch(value):
            return True
        if EMOJI_ONLY_RE.fullmatch(value) and not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", value):
            return True
        return False

    def _remove_mentions(self, text: str) -> str:
        return MENTION_RE.sub(" ", text or "").strip()

    def _clean_name(self, text: str) -> str:
        value = URL_RE.sub(" ", text or "")
        value = MENTION_RE.sub(" ", value)
        value = re.sub(r"(共|總共|合計|小計)\s*\d+\s*(元)?", " ", value)
        value = re.sub(r"\s+", " ", value)
        value = value.strip(" ：:-＝=,，。.!！?？()（）[]【】")
        return value.strip()

    @staticmethod
    def _merge_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, int] = {}
        for item in items:
            name = str(item["name"]).strip()
            merged[name] = merged.get(name, 0) + int(item.get("qty", 1))
        return [{"name": name, "qty": qty} for name, qty in merged.items()]

    @staticmethod
    def _chinese_number(value: str) -> int:
        mapping = {"兩": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        return mapping.get(value, 1)
