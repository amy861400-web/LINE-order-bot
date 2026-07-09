import os
import json
import tempfile
from flask import Flask, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from linebot.v3.messaging import MessagingApiBlob

from order_manager import OrderManager
from gemini_ai import GeminiOrderAI

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
orders = OrderManager()
ai = GeminiOrderAI(GEMINI_API_KEY)

@app.route("/")
def home():
    return "LINE Order Bot OK"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    except Exception as e:
        print("ERROR:", repr(e))
    return "OK", 200

def reply(reply_token: str, text: str):
    if not text:
        return
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text[:4900])])
        )

def display_name(event) -> str:
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        try:
            src = event.source
            if getattr(src, "group_id", None):
                p = api.get_group_member_profile(src.group_id, src.user_id)
            elif getattr(src, "room_id", None):
                p = api.get_room_member_profile(src.room_id, src.user_id)
            else:
                p = api.get_profile(src.user_id)
            return p.display_name or src.user_id
        except Exception:
            return getattr(event.source, "user_id", "unknown")

@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event):
    text = (event.message.text or "").strip()
    user_id = getattr(event.source, "user_id", "unknown")
    name = display_name(event)

    if text == "統計":
        reply(event.reply_token, orders.summary())
        return
    if text == "明細":
        reply(event.reply_token, orders.detail())
        return
    if text == "結束":
        orders.stop()
        return
    if text == "清空":
        orders.reset(menu=orders.menu, active=True)
        return

    if not orders.active:
        return

    result = ai.parse_chat(
        message=text,
        user_name=name,
        menu=orders.menu,
        current_orders=orders.public_orders(),
        last_order_user=orders.last_order_user_name,
    )
    orders.apply_ai_result(user_id=user_id, user_name=name, result=result)

@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event):
    with ApiClient(configuration) as api_client:
        blob_api = MessagingApiBlob(api_client)
        content = blob_api.get_message_content(event.message.id)
        image_bytes = content if isinstance(content, (bytes, bytearray)) else content.read()

    menu = ai.parse_menu_image(image_bytes)
    orders.reset(menu=menu, active=True)
    # 貼菜單不回覆，直接開始新一輪

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
