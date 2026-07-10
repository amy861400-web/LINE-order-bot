from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import google.generativeai as genai


IGNORE_EXACT = {
    "謝謝", "謝謝唷", "謝謝你", "感謝", "感恩", "ok", "OK", "收到", "好", "好的",
    "午安", "早安", "晚安", "哈哈", "哈哈哈", "已付款", "付款了", "測試", "測試版",
    "TEST", "test", "不用", "不用了",
}


class GeminiOrderAI:
    def __init__(self, api_key: str | None):
        self.enabled = bool(api_key)
        if self.enabled:
            genai.configure(api_key=api_key)
            # 可用 GEMINI_MODEL 環境變數替換模型名稱。
            import os
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            self.model = genai.GenerativeModel(model_name)

    def parse_chat(
        self,
        message: str,
        user_name: str,
        current_orders: Dict[str, Dict[str, int]],
        last_order_user: str | None = None,
    ) -> Dict[str, Any]:
        msg = self._remove_mentions((message or "").strip())
        if self._quick_ignore(msg):
            return {"action": "ignore"}

        if not self.enabled:
            return self._fallback(msg)

        prompt = f"""
你是台灣公司 LINE 群組的訂餐解析器。只輸出一個 JSON 物件，不要 Markdown、不要解釋。

核心規則：
1. 訂餐人永遠是發訊息的人「{user_name}」，不可改成被 @ 標記的人。
2. 圖片只用來開始新一輪；你不需要也不能依賴菜單。
3. 一般新點餐與分次加點都使用 add，保留先前餐點並累加。
4. 只有訊息明確包含「改、改成、換、換成」時才使用 set，代表覆蓋此人的舊訂單。
5. 「取消、不要了、不用了」使用 cancel。
6. 「一樣、跟上一位一樣、跟某人一樣」使用 copy。
7. 金額、單價、總價、等號、共多少元、謝謝、感恩、麻煩、OK、已付款、emoji、網址、電話、地址、日常聊天都不要列為餐點。
8. 多行訊息可解析多個餐點。數量可能寫成 *2、x2、×2、2份。
9. 如果無法明確判斷為餐點，輸出 ignore。
10. 不要把「測試、測試版、共400、謝謝」當餐點。

只允許以下格式：
{{"action":"ignore"}}
{{"action":"add","items":[{{"name":"餐點名稱","qty":1}}]}}
{{"action":"set","items":[{{"name":"餐點名稱","qty":1}}]}}
{{"action":"cancel"}}
{{"action":"copy","target":"last"}}
{{"action":"copy","target":"對方 LINE 顯示名稱"}}

範例：
訊息：豬腳飯100\n辣腿排飯95\n炒麻油雞飯95
輸出：{{"action":"add","items":[{{"name":"豬腳飯","qty":1}},{{"name":"辣腿排飯","qty":1}},{{"name":"炒麻油雞飯","qty":1}}]}}

訊息：招牌飯90，雞腿飯105x2=210，鮭魚飯105，共405，謝謝
輸出：{{"action":"add","items":[{{"name":"招牌飯","qty":1}},{{"name":"雞腿飯","qty":2}},{{"name":"鮭魚飯","qty":1}}]}}

訊息：改成排骨飯
輸出：{{"action":"set","items":[{{"name":"排骨飯","qty":1}}]}}

訊息：@吉昇家偉 測試版
輸出：{{"action":"ignore"}}

目前訂單：{json.dumps(current_orders, ensure_ascii=False)}
上一位點餐者：{last_order_user}
訊息：{msg}
"""
        try:
            response = self.model.generate_content(prompt)
            data = self._json(response.text)
            return self._sanitize_result(data)
        except Exception as exc:
            print("Gemini chat error:", repr(exc))
            return self._fallback(msg)

    def _sanitize_result(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {"action": "ignore"}
        action = str(data.get("action", "ignore")).strip().lower()
        if action not in {"ignore", "add", "set", "cancel", "copy"}:
            return {"action": "ignore"}
        if action in {"ignore", "cancel"}:
            return {"action": action}
        if action == "copy":
            target = str(data.get("target", "last") or "last").strip()
            return {"action": "copy", "target": target or "last"}

        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            return {"action": "ignore"}
        items: List[Dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            name = self._clean_food_name(str(item.get("name", "")))
            if not name:
                continue
            try:
                qty = int(item.get("qty", 1) or 1)
            except (TypeError, ValueError):
                qty = 1
            if 1 <= qty <= 50:
                items.append({"name": name, "qty": qty})
        if not items:
            return {"action": "ignore"}
        return {"action": action, "items": items}

    def _json(self, text: str) -> Any:
        text = (text or "").strip()
        text = re.sub(r"^```json\s*|^```\s*|```$", "", text, flags=re.I | re.M).strip()
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            text = match.group(0)
        return json.loads(text)

    def _remove_mentions(self, text: str) -> str:
        # LINE 的提及名稱只視為聊天標記；發訊息者仍由 LINE event.source 決定。
        return re.sub(r"@\S+", " ", text or "").strip()

    def _quick_ignore(self, msg: str) -> bool:
        text = (msg or "").strip()
        if not text or text in IGNORE_EXACT:
            return True
        if text in {"統計", "結單", "清空", "結束", "我的訂單"}:
            return True
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
            return True
        if re.fullmatch(r"(共|總共|合計)?\s*\$?\s*\d+\s*(元)?\s*(謝謝)?", text):
            return True
        if re.fullmatch(r"https?://\S+", text, flags=re.I):
            return True
        return False

    def _fallback(self, msg: str) -> Dict[str, Any]:
        text = (msg or "").strip()
        if self._quick_ignore(text):
            return {"action": "ignore"}
        if any(word in text for word in ("取消", "不要了", "不用了")):
            return {"action": "cancel"}
        if "一樣" in text:
            target = text.replace("跟", "").replace("上一位", "").replace("一樣", "").strip()
            return {"action": "copy", "target": target or "last"}

        action = "add"
        if text.startswith(("改成", "換成")):
            text = text[2:].strip()
            action = "set"
        elif text.startswith(("改", "換")):
            text = text[1:].strip()
            action = "set"
        elif text.startswith(("再加",)):
            text = text[2:].strip()
        elif text.startswith(("加", "+")):
            text = text[1:].strip()

        items = self._simple_extract_items(text)
        return {"action": action, "items": items} if items else {"action": "ignore"}

    def _simple_extract_items(self, text: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for raw in re.split(r"[\n,，、]+", text):
            line = self._remove_mentions(raw).strip()
            if not line or self._quick_ignore(line):
                continue
            if re.fullmatch(r"(共|總共|合計)\s*\$?\s*\d+\s*(元)?\s*(謝謝)?", line):
                continue

            qty = 1
            m = re.search(r"[*xX×]\s*(\d+)", line)
            if m:
                qty = int(m.group(1))
            else:
                m = re.search(r"(\d+)\s*份", line)
                if m:
                    qty = int(m.group(1))

            # 先移除價格乘數算式，再移除單價與數量符號。
            line = re.sub(r"\$?\s*\d+\s*[*xX×]\s*\d+\s*=\s*\d+", " ", line)
            line = re.sub(r"\$?\s*\d+\s*(元)?", " ", line)
            line = re.sub(r"[*xX×]\s*\d+", " ", line)
            for word in ("我要", "請問", "麻煩", "感恩", "謝謝", "OK", "ok", "共", "總共", "合計"):
                line = line.replace(word, " ")
            name = self._clean_food_name(line)
            if name:
                items.append({"name": name, "qty": qty})
        return items

    def _clean_food_name(self, name: str) -> str:
        text = (name or "").strip()
        text = self._remove_mentions(text)
        text = re.sub(r"https?://\S+", " ", text, flags=re.I)
        text = re.sub(r"(共|總共|合計)\s*\$?\s*\d+\s*(元)?", " ", text)
        text = re.sub(r"\$?\s*\d+\s*(元)?", " ", text)
        for word in ("謝謝", "感謝", "感恩", "麻煩", "收到", "已付款"):
            text = text.replace(word, " ")
        text = re.sub(r"\s+", " ", text).strip(" ：:-＝=,，。.!！?？")
        if not text or text in IGNORE_EXACT or text.isdigit():
            return ""
        if text.lower() in {"test", "testing", "測試", "測試版"}:
            return ""
        return text
