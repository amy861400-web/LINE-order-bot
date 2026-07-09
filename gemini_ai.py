import json
import re
import google.generativeai as genai

class GeminiOrderAI:
    def __init__(self, api_key: str | None):
        self.enabled = bool(api_key)
        if self.enabled:
            genai.configure(api_key=api_key)
            self.text_model = genai.GenerativeModel("gemini-1.5-flash")
            self.vision_model = genai.GenerativeModel("gemini-1.5-flash")

    def parse_menu_image(self, image_bytes: bytes):
        if not self.enabled:
            return []
        prompt = """
你是台灣便當/餐點菜單辨識助手。請從圖片中讀取菜單品項與價格。
只輸出 JSON array，例如：[{"name":"豬腳飯","price":100}]。
看不清楚也盡量輸出你能辨識的品項。不要輸出其他文字。
"""
        try:
            resp = self.vision_model.generate_content([
                prompt,
                {"mime_type": "image/jpeg", "data": image_bytes}
            ])
            data = self._json(resp.text)
            return data if isinstance(data, list) else []
        except Exception as e:
            print("Gemini image error:", repr(e))
            return []

    def parse_chat(self, message: str, user_name: str, menu, current_orders, last_order_user=None):
        # 沒有 Gemini 時，先用簡易規則，避免完全不能用
        if not self.enabled:
            return self._fallback(message)

        prompt = f"""
你是 LINE 群組訂餐 AI。請判斷這句話是不是點餐、改單、取消、加點、跟別人一樣，或只是聊天。
只輸出 JSON，不要說明。

回傳格式只能是以下其中一種：
{{"action":"ignore"}}
{{"action":"order","order":"餐點名稱","note":"備註，可空白"}}
{{"action":"update","order":"新的餐點","note":"備註，可空白"}}
{{"action":"add_note","note":"加點或備註"}}
{{"action":"cancel"}}
{{"action":"copy","target":"要跟誰一樣；如果只是說一樣而沒有指名，可用 last"}}

判斷規則：
- 日常聊天、問候、閒聊 → ignore。
- 「我要豬腳」「豬腳飯」「牛肉麵不要蔥」→ order。
- 「改雞腿飯」→ update。
- 「取消」「不要了」→ cancel。
- 「加蛋」「+滷蛋」「大碗」「不要香菜」→ add_note。
- 「跟小明一樣」「一樣」→ copy。
- 若菜單有相近品項，請補成完整品項，例如「豬腳」可能是「豬腳飯」。

目前菜單：{json.dumps(menu, ensure_ascii=False)}
目前訂單：{json.dumps(current_orders, ensure_ascii=False)}
上一位點餐者：{last_order_user}
發言者：{user_name}
訊息：{message}
"""
        try:
            resp = self.text_model.generate_content(prompt)
            data = self._json(resp.text)
            return data if isinstance(data, dict) else {"action": "ignore"}
        except Exception as e:
            print("Gemini chat error:", repr(e))
            return self._fallback(message)

    def _json(self, text: str):
        text = text.strip()
        text = re.sub(r"^```json\s*|```$", "", text, flags=re.I | re.M).strip()
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if m:
            text = m.group(1)
        return json.loads(text)

    def _fallback(self, msg: str):
        t = msg.strip()
        if not t or t in ("統計", "明細", "清空", "結束"):
            return {"action":"ignore"}
        if any(x in t for x in ["取消", "不要了", "不用了"]):
            return {"action":"cancel"}
        if "一樣" in t or "跟" in t and "一樣" in t:
            target = t.replace("跟", "").replace("一樣", "").strip() or "last"
            return {"action":"copy", "target": target}
        if t.startswith(("改", "換")):
            return {"action":"update", "order": t[1:].strip(), "note":""}
        if t.startswith(("+", "加")) or t.startswith(("不要", "去", "少")):
            return {"action":"add_note", "note": t}
        if any(k in t for k in ["飯", "麵", "便當", "湯", "水餃", "滷蛋", "雞", "牛", "豬", "魚", "排骨"]):
            return {"action":"order", "order": t, "note":""}
        return {"action":"ignore"}
