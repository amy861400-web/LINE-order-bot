from __future__ import annotations

import json
import re
from typing import Any, Dict, List
import google.generativeai as genai


IGNORE_WORDS = {
    "謝謝", "謝謝唷", "謝謝你", "感謝", "共", "合計", "總共", "ok", "OK", "收到", "好", "好的",
    "午安", "哈哈", "哈哈哈", "已付款", "付款了", "不用", "不用了"
}


class GeminiOrderAI:
    def __init__(self, api_key: str | None):
        self.enabled = bool(api_key)
        if self.enabled:
            genai.configure(api_key=api_key)
            self.text_model = genai.GenerativeModel("gemini-1.5-flash")
            self.vision_model = genai.GenerativeModel("gemini-1.5-flash")

    def analyze_image(self, image_bytes: bytes) -> Dict[str, Any]:
        if not self.enabled:
            return {"image_type": "unknown", "confidence": 0, "menu": []}

        prompt = """
你是台灣公司 LINE 群組訂餐機器人。請判斷圖片是不是「餐點菜單」。
只輸出 JSON，不要說明。

若是便當、餐廳、飲料、麵店、早餐店等菜單，輸出：
{"image_type":"menu","confidence":0.95,"menu":[{"name":"二寶飯","price":100}]}

若是 Excel、餐費統計表、結餘表、報表、對話截圖、照片、貼圖、非菜單圖片，輸出：
{"image_type":"not_menu","confidence":0.95,"menu":[]}

判斷重點：
- 菜單通常有多個餐點名稱與價格。
- 統計表、餐費表、金額結餘表不是菜單，必須 not_menu。
- 看不清楚或不確定時，請 not_menu。
"""
        try:
            resp = self.vision_model.generate_content([
                prompt,
                {"mime_type": "image/jpeg", "data": image_bytes}
            ])
            data = self._json(resp.text)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print("Gemini image error:", repr(e))
        return {"image_type": "unknown", "confidence": 0, "menu": []}

    def parse_chat(self, message: str, user_name: str, menu, current_orders, last_order_user=None) -> Dict[str, Any]:
        message = (message or "").strip()
        if self._quick_ignore(message):
            return {"action": "ignore"}

        if not self.enabled:
            return self._fallback(message)

        prompt = f"""
你是台灣 LINE 群組訂餐 AI。請判斷訊息是否為訂餐內容。
只輸出 JSON，不要說明。

可輸出格式只能如下：
{{"action":"ignore"}}
{{"action":"set","items":[{{"name":"餐點名稱","qty":1}}]}}
{{"action":"add","items":[{{"name":"餐點名稱","qty":1}}]}}
{{"action":"cancel"}}
{{"action":"copy","target":"對方 LINE 顯示名稱，若只說一樣則用 last"}}

規則：
1. 日常聊天、謝謝、OK、收到、已付款、共400、合計、總共、emoji、貼圖文字、問候語 → ignore。
2. 訊息中有價格或金額時，只擷取餐點與數量，不要擷取金額。
   例如「二寶飯 $100*2=200」→ {{"action":"set","items":[{{"name":"二寶飯","qty":2}}]}}
   例如「雞排飯 100」→ {{"action":"set","items":[{{"name":"雞排飯","qty":1}}]}}
3. 多行訂單要全部擷取：
   「二寶飯 $100*2=200\n鮭魚飯 $105\n共305\n謝謝」→ 二寶飯 2、鮭魚飯 1，忽略共305與謝謝。
4. 「改雞腿飯」「換雞腿飯」→ set。
5. 「加蛋」「+滷蛋」「再加一份蝦排飯」→ add。
6. 「取消」「不要了」→ cancel。
7. 「跟ANITA一樣」「一樣」→ copy。
8. 如果菜單有相近品項，請補成完整菜名。
9. 不要輸出價格、不要輸出共多少錢、不要輸出謝謝。

目前菜單：{json.dumps(menu, ensure_ascii=False)}
目前訂單：{json.dumps(current_orders, ensure_ascii=False)}
上一位點餐者：{last_order_user}
發言者：{user_name}
訊息：{message}
"""
        try:
            resp = self.text_model.generate_content(prompt)
            data = self._json(resp.text)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print("Gemini chat error:", repr(e))
        return self._fallback(message)

    def _json(self, text: str):
        text = (text or "").strip()
        text = re.sub(r"^```json\s*|```$", "", text, flags=re.I | re.M).strip()
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if m:
            text = m.group(1)
        return json.loads(text)

    def _quick_ignore(self, msg: str) -> bool:
        t = msg.strip()
        if not t:
            return True
        if t in ("統計", "結單", "明細", "清空", "結束"):
            return True
        if t in IGNORE_WORDS:
            return True
        # 幾乎只有 emoji / 符號
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", t):
            return True
        # 單純金額、共400、總共195 這類
        if re.fullmatch(r"(共|總共|合計)?\s*\$?\s*\d+\s*(元)?\s*(謝謝)?", t):
            return True
        return False

    def _fallback(self, msg: str) -> Dict[str, Any]:
        t = msg.strip()
        if self._quick_ignore(t):
            return {"action": "ignore"}
        if any(x in t for x in ["取消", "不要了", "不用了"]):
            return {"action": "cancel"}
        if "一樣" in t:
            target = t.replace("跟", "").replace("一樣", "").strip() or "last"
            return {"action": "copy", "target": target}

        action = "set"
        if t.startswith(("+", "加", "再加")):
            action = "add"
        if t.startswith(("改", "換")):
            t = t[1:].strip()
            action = "set"

        items = self._simple_extract_items(t)
        if items:
            return {"action": action, "items": items}
        return {"action": "ignore"}

    def _simple_extract_items(self, text: str) -> List[Dict[str, Any]]:
        lines = re.split(r"[\n,，、]+", text)
        items = []
        for line in lines:
            s = line.strip()
            if not s or self._quick_ignore(s):
                continue
            if any(w in s for w in ["謝謝", "共", "總共", "合計"]):
                continue

            qty = 1
            m = re.search(r"[*xX×]\s*(\d+)", s)
            if m:
                qty = int(m.group(1))
            else:
                m2 = re.search(r"(\d+)\s*份", s)
                if m2:
                    qty = int(m2.group(1))

            # 移除價格與算式
            s = re.sub(r"\$?\s*\d+\s*[*xX×]\s*\d+\s*=\s*\d+", "", s)
            s = re.sub(r"\$?\s*\d+\s*(元)?", "", s)
            s = re.sub(r"[*xX×]\s*\d+", "", s)
            s = s.replace("我要", "").replace("我 要", "").strip()
            s = s.strip("：: -")
            if s:
                items.append({"name": s, "qty": qty})
        return items
