from __future__ import annotations

import json
import re
from typing import Any, Dict, List
import google.generativeai as genai


IGNORE_WORDS = {
    "謝謝", "謝謝唷", "謝謝你", "感謝",
    "共", "合計", "總共",
    "ok", "OK", "收到", "好", "好的",
    "午安", "早安", "晚安",
    "哈哈", "哈哈哈",
    "已付款", "付款了",
    "不用", "不用了",
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
            return {
                "image_type": "unknown",
                "confidence": 0,
                "menu": []
            }

        prompt = """
你是台灣公司 LINE 群組訂餐機器人。

你的任務：
1. 判斷圖片是不是「餐點菜單」。
2. 如果是菜單，完整擷取真正可以點的餐點名稱與價格。
3. 只輸出 JSON，不要說明。

以下圖片算是 menu：
- 便當店菜單
- 早餐店菜單
- 飲料店菜單
- 麵店菜單
- 餐廳菜單
- 外送菜單
- LINE 貼的餐點菜單截圖
- 有多個餐點名稱與價格的圖片

以下圖片不是 menu，必須輸出 not_menu：
- Excel
- 餐費統計表
- 結餘表
- 報表
- 排班表
- ERP畫面
- 對話截圖
- 自拍
- 風景照
- 公司公告
- 不是餐點菜單的圖片

如果是 menu：
menu 只能保留真正可以點的餐點。

不要放入：
- 店名
- Logo
- 地址
- 電話
- Google Map
- 外送金額
- 滿多少外送
- 活動文字
- 廣告文字
- 白飯加購
- 蔬菜加購
- 免運門檻
- 說明文字
- 日期
- 備註

輸出格式：

{
  "image_type": "menu",
  "confidence": 0.95,
  "menu": [
    {"name": "糖醋里肌", "price": 100},
    {"name": "卡啦雞排", "price": 100},
    {"name": "塔香三杯雞", "price": 100}
  ]
}

如果不是菜單：

{
  "image_type": "not_menu",
  "confidence": 0.95,
  "menu": []
}

如果看不清楚或不確定，請輸出 not_menu。
"""

        try:
            resp = self.vision_model.generate_content([
                prompt,
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            ])

            data = self._json(resp.text)

            if isinstance(data, dict):
                return data

        except Exception as e:
            print("Gemini image error:", repr(e))

        return {
            "image_type": "unknown",
            "confidence": 0,
            "menu": []
        }

    def parse_chat(
        self,
        message: str,
        user_name: str,
        menu,
        current_orders,
        last_order_user=None
    ) -> Dict[str, Any]:

        message = (message or "").strip()

        if self._quick_ignore(message):
            return {"action": "ignore"}

        clean_message = self._remove_mentions(message)

        if self._quick_ignore(clean_message):
            return {"action": "ignore"}

        if not self.enabled:
            return self._fallback(clean_message)

        prompt = f"""
你是台灣 LINE 群組訂餐 AI。

請判斷訊息是否為訂餐內容。

只輸出 JSON，不要說明。

重要原則：
1. 訂餐人永遠是發訊息的人。
2. 訊息中的 @某某某 只是標記，不是訂餐人。
3. 你只能解析餐點，不可以改變訂餐人。
4. 不是目前菜單內的品項，不可以加入訂單。
5. 不可以把整份菜單當成使用者訂單。
6. 使用者沒有明確點的餐點，不可以加入。
7. items 最多只能包含使用者實際點的餐點。
8. 日常聊天、測試文字、謝謝、OK、收到、已付款、共400、emoji、網址、電話、地址，全部 ignore。
9. 訊息中有價格或金額，只擷取餐點與數量，不要擷取金額。
10. 如果訊息包含「謝謝」「感恩」「麻煩」「OK」，請忽略這些字，只留下餐點。
11. 如果訊息只有金額或共多少元，請 ignore。
12. 如果訊息是「測試版」，但目前菜單沒有「測試版」，請 ignore。
13. 如果訊息是「@某人 測試版」，且菜單沒有「測試版」，請 ignore。
14. 如果訊息是「@某人 雞腿飯」，且菜單有「雞腿飯」，請輸出雞腿飯，不要輸出 @某人。
15. 如果使用者打簡稱、錯字、同音字，請嘗試對應目前菜單內最接近的品項。
16. 如果無法明確對應目前菜單品項，請 ignore。

可輸出格式只能如下：

{{"action":"ignore"}}

{{"action":"set","items":[{{"name":"餐點名稱","qty":1}}]}}

{{"action":"add","items":[{{"name":"餐點名稱","qty":1}}]}}

{{"action":"cancel"}}

{{"action":"copy","target":"對方 LINE 顯示名稱，若只說一樣則用 last"}}

範例：

訊息：
塔香三杯雞 =100謝謝

如果菜單有「塔香三杯雞」，輸出：
{{"action":"set","items":[{{"name":"塔香三杯雞","qty":1}}]}}

不可以輸出其它菜單品項。

訊息：
二寶飯 $100*2=200
鮭魚飯 $105
共305
謝謝

如果菜單有二寶飯、鮭魚飯，輸出：
{{"action":"set","items":[{{"name":"二寶飯","qty":2}},{{"name":"鮭魚飯","qty":1}}]}}

訊息：
@吉昇家偉 測試版

如果菜單沒有「測試版」，輸出：
{{"action":"ignore"}}

訊息：
@吉昇家偉 卡啦雞排

如果菜單有「卡啦雞排」，輸出：
{{"action":"set","items":[{{"name":"卡啦雞排","qty":1}}]}}

訊息：
共400

輸出：
{{"action":"ignore"}}

目前菜單：
{json.dumps(menu, ensure_ascii=False)}

目前訂單：
{json.dumps(current_orders, ensure_ascii=False)}

上一位點餐者：
{last_order_user}

發言者：
{user_name}

原始訊息：
{message}

移除 @ 標記後的訊息：
{clean_message}
"""

        try:
            resp = self.text_model.generate_content(prompt)
            data = self._json(resp.text)

            if isinstance(data, dict):
                return data

        except Exception as e:
            print("Gemini chat error:", repr(e))

        return self._fallback(clean_message)

    def _json(self, text: str):
        text = (text or "").strip()
        text = re.sub(r"^```json\s*|```$", "", text, flags=re.I | re.M).strip()

        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)

        if m:
            text = m.group(1)

        return json.loads(text)

    def _quick_ignore(self, msg: str) -> bool:
        t = (msg or "").strip()

        if not t:
            return True

        if t in ("統計", "結單", "明細", "清空", "結束"):
            return True

        if t in IGNORE_WORDS:
            return True

        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", t):
            return True

        if re.fullmatch(r"(共|總共|合計)?\s*\$?\s*\d+\s*(元)?\s*(謝謝)?", t):
            return True

        return False

    def _remove_mentions(self, text: str) -> str:
        text = text or ""

        # 移除 LINE tag，例如 @吉昇家偉、@【吉昇】家偉
        text = re.sub(r"@\S+", "", text)

        return text.strip()

    def _fallback(self, msg: str) -> Dict[str, Any]:
        t = (msg or "").strip()

        if self._quick_ignore(t):
            return {"action": "ignore"}

        if any(x in t for x in ["取消", "不要了", "不用了"]):
            return {"action": "cancel"}

        if "一樣" in t:
            target = t.replace("跟", "").replace("一樣", "").strip() or "last"
            return {
                "action": "copy",
                "target": target
            }

        action = "set"

        if t.startswith(("+", "加", "再加")):
            action = "add"

        if t.startswith(("改", "換")):
            t = t[1:].strip()
            action = "set"

        items = self._simple_extract_items(t)

        if items:
            return {
                "action": action,
                "items": items
            }

        return {"action": "ignore"}

    def _simple_extract_items(self, text: str) -> List[Dict[str, Any]]:
        lines = re.split(r"[\n,，、]+", text)
        items = []

        for line in lines:
            s = line.strip()

            if not s:
                continue

            s = self._remove_mentions(s)

            if self._quick_ignore(s):
                continue

            if any(w in s for w in ["謝謝", "共", "總共", "合計"]):
                s = s.replace("謝謝", "")
                s = s.replace("感謝", "")
                s = s.replace("共", "")
                s = s.replace("總共", "")
                s = s.replace("合計", "")

            qty = 1

            m = re.search(r"[*xX×]\s*(\d+)", s)
            if m:
                qty = int(m.group(1))
            else:
                m2 = re.search(r"(\d+)\s*份", s)
                if m2:
                    qty = int(m2.group(1))

            s = re.sub(r"\$?\s*\d+\s*[*xX×]\s*\d+\s*=\s*\d+", "", s)
            s = re.sub(r"\$?\s*\d+\s*(元)?", "", s)
            s = re.sub(r"[*xX×]\s*\d+", "", s)

            s = s.replace("我要", "")
            s = s.replace("我 要", "")
            s = s.replace("請問", "")
            s = s.replace("麻煩", "")
            s = s.replace("感恩", "")
            s = s.replace("謝謝", "")
            s = s.replace("OK", "")
            s = s.replace("ok", "")

            s = s.strip()
            s = s.strip("：: -＝=")

            if s:
                items.append({
                    "name": s,
                    "qty": qty
                })

        return items
