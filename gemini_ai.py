from __future__ import annotations

import json
import re
from typing import Any, Dict
import google.generativeai as genai

IGNORE_WORDS = {
    "謝謝", "謝謝唷", "感謝", "ok", "OK", "收到", "好", "好的", "午安", "早安", "晚安",
    "哈哈", "哈哈哈", "已付款", "付款了", "不用", "不用了", "測試", "TEST", "test"
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
你是台灣 LINE 訂餐機器人，請判斷圖片是不是餐點菜單，並擷取可點餐點。
只輸出 JSON，不要任何說明。

若是便當、早餐、飲料、麵店、餐廳、外送平台菜單，輸出：
{"image_type":"menu","confidence":0.95,"menu":[{"name":"餐點名稱","price":100}]}

若是 Excel、餐費統計表、結餘表、報表、排班表、ERP、對話截圖、照片、公司公告、不是菜單，輸出：
{"image_type":"not_menu","confidence":0.95,"menu":[]}

菜單擷取規則：
- 只保留真正可點的主餐/餐點/飲料品項。
- 不要店名、Logo、地址、電話、營業時間、外送金額、滿額外送、Google Map、廣告文字、活動文字、日期、備註。
- 不要把「白飯加購、蔬菜加購、免運門檻」當主餐，除非圖片明確是配菜單。
- 每個 name 不要包含價格、$、元。
- price 沒看清楚可填 null。
- 如果看起來是菜單但文字很小，也盡量擷取能看清楚的餐點。
"""
        try:
            resp = self.vision_model.generate_content([prompt, {"mime_type": "image/jpeg", "data": image_bytes}])
            data = self._json(resp.text)
            if isinstance(data, dict):
                return self._sanitize_menu_result(data)
        except Exception as e:
            print("Gemini image error:", repr(e))
        return {"image_type": "unknown", "confidence": 0, "menu": []}

    def parse_chat(self, message: str, user_name: str, menu, current_orders, last_order_user=None) -> Dict[str, Any]:
        msg = self._remove_mentions((message or "").strip())
        if self._quick_ignore(msg):
            return {"action": "ignore"}
        if not self.enabled:
            return self._fallback(msg)
        menu_names = [x.get("name") for x in menu if x.get("name")]
        prompt = f"""
你是台灣 LINE 訂餐 AI。只輸出 JSON，不要說明。

重要規則：
1. 訂餐人永遠是發訊息的人，不是 @ 標記的人。
2. @某人只是聊天標記，已經從訊息中移除，不可當餐點。
3. 只能擷取使用者明確點的餐點，不能把整份菜單輸出。
4. 餐點必須能對應目前菜單；不能對應菜單就 ignore。
5. 測試版、謝謝、共400、OK、已付款、emoji、網址、電話、地址、日常聊天都 ignore。
6. 價格與金額要忽略，只保留餐點與數量。
7. 可做模糊修正：三杯雞→塔香三杯雞、卡拉雞排→卡啦雞排、牛肉免→牛肉麵。
8. 多行訂單可擷取多個餐點。
9. 如果是「改/換」用 set；「加/再加/+」用 add；「取消/不要了」用 cancel；「一樣/跟某人一樣」用 copy。

可輸出：
{{"action":"ignore"}}
{{"action":"set","items":[{{"name":"菜單內完整餐點名","qty":1}}]}}
{{"action":"add","items":[{{"name":"菜單內完整餐點名","qty":1}}]}}
{{"action":"cancel"}}
{{"action":"copy","target":"last或對方LINE顯示名稱"}}

目前菜單品項：{json.dumps(menu_names, ensure_ascii=False)}
目前訂單：{json.dumps(current_orders, ensure_ascii=False)}
上一位點餐者：{last_order_user}
發言者：{user_name}
訊息：{msg}
"""
        try:
            resp = self.text_model.generate_content(prompt)
            data = self._json(resp.text)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print("Gemini chat error:", repr(e))
        return self._fallback(msg)

    def _sanitize_menu_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        menu = []
        bad = ["地址", "電話", "外送", "Google", "map", "營業", "滿", "免運", "加購", "白飯", "蔬菜", "Logo"]
        for item in data.get("menu", []) or []:
            if not isinstance(item, dict):
                continue
            name = re.sub(r"[$＄]?\s*\d+\s*(元)?", "", str(item.get("name", ""))).strip()
            name = re.sub(r"\s+", "", name)
            if len(name) < 2 or any(b in name for b in bad):
                continue
            price = item.get("price")
            try:
                price = int(price) if price not in (None, "") else None
            except Exception:
                price = None
            menu.append({"name": name, "price": price})
        return {"image_type": data.get("image_type", "unknown"), "confidence": float(data.get("confidence", 0) or 0), "menu": menu}

    def _json(self, text: str):
        text = (text or "").strip()
        text = re.sub(r"^```json\s*|```$", "", text, flags=re.I | re.M).strip()
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if m:
            text = m.group(1)
        return json.loads(text)

    def _remove_mentions(self, text: str) -> str:
        return re.sub(r"@\S+", "", text or "").strip()

    def _quick_ignore(self, msg: str) -> bool:
        t = (msg or "").strip()
        if not t or t in ("統計", "結單", "清空", "結束") or t in IGNORE_WORDS:
            return True
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", t):
            return True
        if re.fullmatch(r"(共|總共|合計)?\s*\$?\s*\d+\s*(元)?\s*(謝謝)?", t):
            return True
        return False

    def _fallback(self, msg: str) -> Dict[str, Any]:
        if self._quick_ignore(msg):
            return {"action": "ignore"}
        if any(x in msg for x in ["取消", "不要了", "不用了"]):
            return {"action": "cancel"}
        if "一樣" in msg:
            target = msg.replace("跟", "").replace("一樣", "").strip() or "last"
            return {"action": "copy", "target": target}
        action = "set"
        if msg.startswith(("+", "加", "再加")):
            action = "add"
        if msg.startswith(("改", "換")):
            msg = msg[1:].strip()
            action = "set"
        return {"action": action, "items": self._simple_extract_items(msg)}

    def _simple_extract_items(self, text: str):
        out = []
        for line in re.split(r"[\n,，、]+", text):
            s = self._remove_mentions(line).strip()
            if self._quick_ignore(s):
                continue
            qty = 1
            m = re.search(r"[*xX×]\s*(\d+)", s)
            if m:
                qty = int(m.group(1))
            m2 = re.search(r"(\d+)\s*份", s)
            if m2:
                qty = int(m2.group(1))
            s = re.sub(r"\$?\s*\d+\s*[*xX×]\s*\d+\s*=\s*\d+", "", s)
            s = re.sub(r"\$?\s*\d+\s*(元)?", "", s)
            s = re.sub(r"[*xX×]\s*\d+", "", s)
            for w in ["我要", "請問", "麻煩", "感恩", "謝謝", "OK", "ok", "共", "總共", "合計"]:
                s = s.replace(w, "")
            s = s.strip(" ：:-＝=")
            if s:
                out.append({"name": s, "qty": qty})
        return out
