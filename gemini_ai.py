from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import google.generativeai as genai


IGNORE_WORDS = {
    "謝謝", "謝謝唷", "謝謝你", "感謝", "感恩", "麻煩", "謝啦",
    "共", "合計", "總共", "ok", "OK", "收到", "好", "好的",
    "午安", "早安", "晚安", "哈哈", "哈哈哈", "已付款", "付款了",
    "不用", "不用了", "測試", "TEST", "test",
}


class GeminiOrderAI:
    def __init__(self, api_key: str | None):
        self.enabled = bool(api_key)
        if self.enabled:
            genai.configure(api_key=api_key)
            # flash 速度快、成本低；若帳號支援新版模型也可改 gemini-1.5-flash 或 gemini-2.0-flash
            self.text_model = genai.GenerativeModel("gemini-1.5-flash")
            self.vision_model = genai.GenerativeModel("gemini-1.5-flash")

    def analyze_image(self, image_bytes: bytes) -> Dict[str, Any]:
        if not self.enabled:
            return {"image_type": "unknown", "confidence": 0, "menu": []}

        prompt = """
你是台灣公司 LINE 群組訂餐機器人。
請判斷圖片是不是「餐點菜單」。

只輸出 JSON，不要說明。

若是便當、餐廳、飲料、麵店、早餐店等菜單，輸出：
{"image_type":"menu","confidence":0.95,"menu":[{"name":"二寶飯","price":100},{"name":"雞腿飯","price":95}]}

若是 Excel、餐費統計表、結餘表、報表、對話截圖、照片、貼圖、非菜單圖片，輸出：
{"image_type":"not_menu","confidence":0.95,"menu":[]}

規則：
1. 菜單通常有多個餐點名稱與價格。
2. 統計表、餐費表、金額結餘表不是菜單，必須 not_menu。
3. 若圖片只是訂單統計、收支表、結餘表、Excel 表格，必須 not_menu。
4. 看不清楚、不確定時，請 not_menu。
5. 菜單名稱不要包含價格、符號、編號，只保留餐點名稱。
"""
        try:
            resp = self.vision_model.generate_content(
                [
                    prompt,
                    {"mime_type": "image/jpeg", "data": image_bytes},
                ]
            )
            data = self._json(resp.text)
            if isinstance(data, dict):
                return data

        except Exception as e:
            print("Gemini image error:", repr(e))

        return {"image_type": "unknown", "confidence": 0, "menu": []}

    def parse_chat(
        self,
        message: str,
        user_name: str,
        menu,
        current_orders,
        last_order_user=None,
    ) -> Dict[str, Any]:
        message = (message or "").strip()

        if self._quick_ignore(message):
            return {"action": "ignore"}

        cleaned_message = self._remove_line_mentions(message)

        if self._quick_ignore(cleaned_message):
            return {"action": "ignore"}

        if not self.enabled:
            return self._fallback(cleaned_message)

        menu_names = [str(x.get("name", "")).strip() for x in menu or [] if str(x.get("name", "")).strip()]

        prompt = f"""
你是台灣 LINE 群組訂餐 AI。
請判斷訊息是否為訂餐內容，並只擷取「目前菜單中存在的餐點」。

只輸出 JSON，不要說明。

可輸出格式只能如下：
{{"action":"ignore"}}
{{"action":"set","items":[{{"name":"餐點名稱","qty":1}}]}}
{{"action":"add","items":[{{"name":"餐點名稱","qty":1}}]}}
{{"action":"cancel"}}
{{"action":"copy","target":"對方 LINE 顯示名稱，若只說一樣則用 last"}}

重要規則：
1. 訂餐人永遠是發訊息的人，不是 @ 標記的人。
2. @某人、LINE標記、稱呼，只是聊天內容，不可以當訂餐人，也不可以當餐點。
3. 只有目前菜單裡存在的品項，才可以輸出到 items。
4. 不是菜單品項的內容，一律 ignore 或排除。
5. 絕對不能把整份菜單當成使用者訂單。
6. 使用者沒有明確點的餐點，不可以加入。
7. items 最多只能包含使用者實際點的餐點，不可以因為 menu 裡存在而全部輸出。
8. 日常聊天、謝謝、OK、收到、已付款、共400、合計、總共、emoji、問候語、測試文字、網址、電話、地址 → ignore。
9. 訊息中有價格或金額時，只擷取餐點與數量，不要擷取金額。
   例如「二寶飯 $100*2=200」→ {{"action":"set","items":[{{"name":"二寶飯","qty":2}}]}}
   例如「雞排飯 100」→ {{"action":"set","items":[{{"name":"雞排飯","qty":1}}]}}
   例如「塔香三杯雞 =100謝謝」→ {{"action":"set","items":[{{"name":"塔香三杯雞","qty":1}}]}}
10. 多行訂單要全部擷取，但只擷取菜單內品項：
   「二寶飯 $100*2=200\\n鮭魚飯 $105\\n共305\\n謝謝」→ 二寶飯 2、鮭魚飯 1。
11. 「改雞腿飯」「換雞腿飯」→ set。
12. 「加蛋」「+滷蛋」「再加一份蝦排飯」→ add，但品項必須在菜單內。
13. 「取消」「不要了」→ cancel。
14. 「跟ANITA一樣」「一樣」→ copy。
15. 若使用者輸入簡稱、錯字、同音字，必須對應到菜單內最接近品項。
   例如菜單有「塔香三杯雞」，訊息「三杯雞」→ 塔香三杯雞。
   例如菜單有「牛肉麵」，訊息「牛肉免」→ 牛肉麵。
16. 若無法合理對應到菜單內品項 → ignore。

目前菜單品項：{json.dumps(menu_names, ensure_ascii=False)}
目前訂單：{json.dumps(current_orders, ensure_ascii=False)}
上一位點餐者：{last_order_user}
發言者：{user_name}
原始訊息：{message}
移除 @ 後訊息：{cleaned_message}
"""
        try:
            resp = self.text_model.generate_content(prompt)
            data = self._json(resp.text)
            if isinstance(data, dict):
                return data

        except Exception as e:
            print("Gemini chat error:", repr(e))

        return self._fallback(cleaned_message)

    def _json(self, text: str):
        text = (text or "").strip()
        text = re.sub(r"^```json\s*|```$", "", text, flags=re.I | re.M).strip()
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if m:
            text = m.group(1)
        return json.loads(text)

    def _remove_line_mentions(self, msg: str) -> str:
        # 移除 LINE tag / @稱呼。訂餐人由 LINE API 取得，不能從文字中的 @ 判斷。
        t = msg or ""
        t = re.sub(r"@[\S]+", " ", t)
        # 常見：@【吉昇】家偉 這類格式會被 @[\S]+ 移除；保守再清一次。
        t = re.sub(r"@[^ \n\r\t]+", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    def _quick_ignore(self, msg: str) -> bool:
        t = (msg or "").strip()
        if not t:
            return True

        if t in ("統計", "結單", "明細", "清空", "結束"):
            return True

        if t in IGNORE_WORDS:
            return True

        # 幾乎只有 emoji / 符號
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", t):
            return True

        # 單純 tag
        if re.fullmatch(r"@.+", t):
            return True

        # 單純金額、共400、總共195 這類
        if re.fullmatch(r"(共|總共|合計)?\s*\$?\s*\d+\s*(元)?\s*(謝謝|感謝|感恩)?", t):
            return True

        # URL
        if re.search(r"https?://|www\.", t, re.I):
            return True

        return False

    def _fallback(self, msg: str) -> Dict[str, Any]:
        t = self._remove_line_mentions((msg or "").strip())

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
            s = self._remove_line_mentions(line.strip())
            if not s or self._quick_ignore(s):
                continue

            if any(w in s for w in ["謝謝", "感謝", "感恩", "共", "總共", "合計"]):
                # 若同一行前面還有餐點，例如「塔香三杯雞 =100謝謝」，先保留謝謝前面。
                s = re.split(r"謝謝|感謝|感恩|共|總共|合計", s)[0].strip()
                if not s:
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
            s = re.sub(r"=\s*\d+", "", s)
            s = re.sub(r"\$?\s*\d+\s*(元)?", "", s)
            s = re.sub(r"[*xX×]\s*\d+", "", s)
            s = s.replace("我要", "").replace("我 要", "").strip()
            s = s.strip("：: -，,。.")

            if s:
                items.append({"name": s, "qty": qty})

        return items
