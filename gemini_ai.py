from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import google.generativeai as genai


IGNORE_WORDS = {
    "謝謝",
    "謝謝唷",
    "謝謝你",
    "感謝",
    "ok",
    "OK",
    "收到",
    "好",
    "好的",
    "午安",
    "早安",
    "晚安",
    "哈哈",
    "哈哈哈",
    "已付款",
    "付款了",
    "不用",
    "不用了",
    "測試",
    "TEST",
    "test",
}


class GeminiOrderAI:
    def __init__(self, api_key: str | None):
        self.enabled = bool(api_key)

        if self.enabled:
            genai.configure(api_key=api_key)
            self.text_model = genai.GenerativeModel("gemini-1.5-flash")

    def analyze_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        現在不分析圖片內容。
        app.py 收到任何圖片時，會直接開始新一輪。
        保留此方法只是為了相容舊版 app.py。
        """
        return {
            "image_type": "new_round",
            "confidence": 1.0,
            "menu": [],
        }

    def parse_chat(
        self,
        message: str,
        user_name: str,
        menu,
        current_orders,
        last_order_user=None,
    ) -> Dict[str, Any]:

        msg = self._remove_mentions((message or "").strip())

        if self._quick_ignore(msg):
            return {"action": "ignore"}

        if not self.enabled:
            return self._fallback(msg)

        prompt = f"""
你是台灣 LINE 群組訂餐 AI。

只輸出 JSON，不要說明，不要使用 Markdown。

重要規則：

1. 訂餐人永遠是發訊息的人，不是被 @ 標記的人。
2. @某人只是聊天標記，已從訊息中移除。
3. 不需要比對菜單。
4. 不分析圖片。
5. 只要訊息能明確判斷為餐點，就加入訂單。
6. 日常聊天、謝謝、OK、收到、已付款、共400、emoji、網址、電話、地址、測試文字都忽略。
7. 金額、單價、總價、等號、謝謝等文字不要當成餐點。
8. 多行內容可以擷取多個餐點。
9. 數量格式可能是 *2、x2、×2、2份。
10. 「改」「換」代表 set。
11. 「加」「再加」「+」代表 add。
12. 「取消」「不要了」「不用了」代表 cancel。
13. 「一樣」「跟某人一樣」代表 copy。
14. 不可以把「共400」「總共195」「謝謝」放進餐點名稱。
15. 不可以把整段聊天當成餐點。
16. 如果無法明確判斷是餐點，輸出 ignore。

只允許輸出以下 JSON 格式之一：

{{"action":"ignore"}}

{{"action":"set","items":[{{"name":"餐點名稱","qty":1}}]}}

{{"action":"add","items":[{{"name":"餐點名稱","qty":1}}]}}

{{"action":"cancel"}}

{{"action":"copy","target":"last"}}

{{"action":"copy","target":"對方 LINE 顯示名稱"}}

範例一：

訊息：
塔香三杯雞 =100謝謝

輸出：
{{"action":"set","items":[{{"name":"塔香三杯雞","qty":1}}]}}

範例二：

訊息：
二寶飯 $100*2=200
鮭魚飯 $105
辣雞排飯 $95
共400
謝謝

輸出：
{{"action":"set","items":[
{{"name":"二寶飯","qty":2}},
{{"name":"鮭魚飯","qty":1}},
{{"name":"辣雞排飯","qty":1}}
]}}

範例三：

訊息：
@吉昇家偉 測試版

如果「測試版」明顯不是餐點，輸出：
{{"action":"ignore"}}

範例四：

訊息：
雞腿飯100
蝦排飯95
共195 謝謝

輸出：
{{"action":"set","items":[
{{"name":"雞腿飯","qty":1}},
{{"name":"蝦排飯","qty":1}}
]}}

目前訂單：
{json.dumps(current_orders, ensure_ascii=False)}

上一位點餐者：
{last_order_user}

發言者：
{user_name}

訊息：
{msg}
"""

        try:
            response = self.text_model.generate_content(prompt)
            data = self._json(response.text)

            if isinstance(data, dict):
                return self._sanitize_result(data)

        except Exception as exc:
            print("Gemini chat error:", repr(exc))

        return self._fallback(msg)

    def _sanitize_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        action = str(data.get("action", "ignore")).strip().lower()

        if action not in {"ignore", "set", "add", "cancel", "copy"}:
            return {"action": "ignore"}

        if action in {"ignore", "cancel"}:
            return {"action": action}

        if action == "copy":
            target = str(data.get("target", "last") or "last").strip()
            return {
                "action": "copy",
                "target": target or "last",
            }

        items = data.get("items", [])

        if not isinstance(items, list):
            return {"action": "ignore"}

        cleaned_items: List[Dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            name = self._clean_food_name(str(item.get("name", "")))

            if not name:
                continue

            try:
                qty = int(item.get("qty", 1) or 1)
            except Exception:
                qty = 1

            if qty <= 0 or qty > 50:
                continue

            cleaned_items.append({
                "name": name,
                "qty": qty,
            })

        if not cleaned_items:
            return {"action": "ignore"}

        return {
            "action": action,
            "items": cleaned_items,
        }

    def _json(self, text: str):
        text = (text or "").strip()

        text = re.sub(
            r"^```json\s*|^```\s*|```$",
            "",
            text,
            flags=re.I | re.M,
        ).strip()

        match = re.search(r"\{.*\}", text, re.S)

        if match:
            text = match.group(0)

        return json.loads(text)

    def _remove_mentions(self, text: str) -> str:
        """
        移除 LINE @標記文字。
        訂餐人仍由 app.py 的 event.source.user_id 決定。
        """
        text = text or ""
        text = re.sub(r"@\S+", "", text)
        return text.strip()

    def _quick_ignore(self, msg: str) -> bool:
        text = (msg or "").strip()

        if not text:
            return True

        if text in ("統計", "結單", "清空", "結束"):
            return True

        if text in IGNORE_WORDS:
            return True

        # 只有 emoji 或符號
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
            return True

        # 純金額或合計
        if re.fullmatch(
            r"(共|總共|合計)?\s*\$?\s*\d+\s*(元)?\s*(謝謝)?",
            text,
        ):
            return True

        # 網址
        if re.fullmatch(r"https?://\S+", text, flags=re.I):
            return True

        return False

    def _fallback(self, msg: str) -> Dict[str, Any]:
        text = (msg or "").strip()

        if self._quick_ignore(text):
            return {"action": "ignore"}

        if any(word in text for word in ["取消", "不要了", "不用了"]):
            return {"action": "cancel"}

        if "一樣" in text:
            target = (
                text.replace("跟", "")
                .replace("一樣", "")
                .strip()
                or "last"
            )

            return {
                "action": "copy",
                "target": target,
            }

        action = "set"

        if text.startswith(("+", "加", "再加")):
            action = "add"

        if text.startswith(("改", "換")):
            text = text[1:].strip()
            action = "set"

        items = self._simple_extract_items(text)

        if not items:
            return {"action": "ignore"}

        return {
            "action": action,
            "items": items,
        }

    def _simple_extract_items(self, text: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        for raw_line in re.split(r"[\n,，、]+", text):
            line = self._remove_mentions(raw_line).strip()

            if not line or self._quick_ignore(line):
                continue

            if re.fullmatch(
                r"(共|總共|合計)\s*\$?\s*\d+\s*(元)?\s*(謝謝)?",
                line,
            ):
                continue

            qty = 1

            quantity_match = re.search(r"[*xX×]\s*(\d+)", line)

            if quantity_match:
                qty = int(quantity_match.group(1))
            else:
                share_match = re.search(r"(\d+)\s*份", line)

                if share_match:
                    qty = int(share_match.group(1))

            # 移除完整金額算式，例如 $100*2=200
            line = re.sub(
                r"\$?\s*\d+\s*[*xX×]\s*\d+\s*=\s*\d+",
                "",
                line,
            )

            # 移除價格，例如 $100、100元、100
            line = re.sub(r"\$?\s*\d+\s*(元)?", "", line)

            # 移除數量，例如 *2
            line = re.sub(r"[*xX×]\s*\d+", "", line)

            for word in [
                "我要",
                "請問",
                "麻煩",
                "感恩",
                "謝謝",
                "OK",
                "ok",
                "共",
                "總共",
                "合計",
            ]:
                line = line.replace(word, "")

            name = self._clean_food_name(line)

            if not name:
                continue

            items.append({
                "name": name,
                "qty": qty,
            })

        return items

    def _clean_food_name(self, name: str) -> str:
        text = (name or "").strip()

        for word in [
            "謝謝",
            "感謝",
            "感恩",
            "麻煩",
            "共",
            "總共",
            "合計",
            "已付款",
            "收到",
        ]:
            text = text.replace(word, "")

        text = re.sub(r"https?://\S+", "", text, flags=re.I)
        text = re.sub(r"\$?\s*\d+\s*(元)?", "", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip(" ：:-＝=,，。.!！")

        if not text:
            return ""

        if text in IGNORE_WORDS:
            return ""

        if text.isdigit():
            return ""

        return text
