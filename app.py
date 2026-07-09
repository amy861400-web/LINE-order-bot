from __future__ import annotations

import os
from flask import Flask, request

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
)

from order_manager import OrderManager
from gemini_ai import GeminiOrderAI


app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ADMIN_LINE_NAMES = [
    x.strip()
    for x in os.getenv("ADMIN_LINE_NAMES", "").split(",")
    if x.strip()
]

# 若設為 true，統計/結單都限制管理員；預設 false，只限制結單。
ADMIN_ONLY_STATS = os.getenv("ADMIN_ONLY_STATS", "false").lower() == "true"

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

orders = OrderManager()
ai = GeminiOrderAI(GEMINI_API_KEY)


@app.route("/")
def home():
    return "LINE Order Bot v4 OK"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    except Exception as e:
        print("callback error:", repr(e))

    return "OK", 200


def reply(reply_token: str, text: str):
    if not text:
        return

    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text[:4900])],
            )
        )


def get_display_name(event) -> str:
    src = event.source
    user_id = getattr(src, "user_id", "unknown")

    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)

        try:
            group_id = getattr(src, "group_id", None)
            room_id = getattr(src, "room_id", None)

            if group_id:
                profile = api.get_group_member_profile(group_id, user_id)
            elif room_id:
                profile = api.get_room_member_profile(room_id, user_id)
            else:
                profile = api.get_profile(user_id)

            return profile.display_name or user_id

        except Exception as e:
            print("profile error:", repr(e))
            return user_id


def is_admin(display_name: str) -> bool:
    if not ADMIN_LINE_NAMES:
        return True
    return display_name in ADMIN_LINE_NAMES


def can_show_summary(command: str, display_name: str) -> bool:
    if command == "結單":
        return is_admin(display_name)
    if command == "統計" and ADMIN_ONLY_STATS:
        return is_admin(display_name)
    return True


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event):
    raw_text = event.message.text or ""
    text = raw_text.strip()
    user_id = getattr(event.source, "user_id", "unknown")
    display_name = get_display_name(event)

    # 只有統計/結單會回覆；其他訊息都安靜處理。
    if text in ("統計", "結單"):
        if can_show_summary(text, display_name):
            reply(event.reply_token, orders.summary())
        return

    # 管理指令：不回覆。
    if text == "清空" and is_admin(display_name):
        orders.reset(menu=orders.menu, active=True)
        return

    if text == "結束" and is_admin(display_name):
        orders.stop()
        return

    if not orders.active:
        return

    # 沒有菜單前，不接受點餐，避免把聊天誤判成餐點。
    if not orders.menu:
        return

    result = ai.parse_chat(
        message=text,
        user_name=display_name,
        menu=orders.menu,
        current_orders=orders.public_orders(),
        last_order_user=orders.last_order_user_name,
    )

    orders.apply_ai_result(
        user_id=user_id,
        user_name=display_name,
        result=result,
    )


@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event):
    # 圖片交給 Gemini 判斷：只有菜單才開始新一輪；報表/統計表/照片/截圖直接忽略。
    try:
        with ApiClient(configuration) as api_client:
            blob_api = MessagingApiBlob(api_client)
            content = blob_api.get_message_content(event.message.id)
            image_bytes = content if isinstance(content, (bytes, bytearray)) else content.read()

        result = ai.analyze_image(image_bytes)
        image_type = result.get("image_type")
        confidence = float(result.get("confidence", 0) or 0)
        menu = result.get("menu", [])

        if image_type == "menu" and confidence >= 0.75 and menu:
            orders.reset_if_new_menu(menu)

    except Exception as e:
        print("image handler error:", repr(e))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
