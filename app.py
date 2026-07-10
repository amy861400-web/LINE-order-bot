from __future__ import annotations

import os
from flask import Flask, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent

from database import OrderDatabase
from gemini_ai import GeminiOrderAI

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ADMIN_LINE_NAMES = {
    name.strip()
    for name in os.getenv("ADMIN_LINE_NAMES", "").split(",")
    if name.strip()
}
DB_PATH = os.getenv("DB_PATH", "orders.db")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
db = OrderDatabase(DB_PATH)
ai = GeminiOrderAI(GEMINI_API_KEY)


@app.get("/")
def home():
    return "LINE Order Bot OK", 200


@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    except Exception as exc:
        print("callback error:", repr(exc))
    return "OK", 200


def reply(reply_token: str, text: str) -> None:
    if not text:
        return
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text[:4900])],
            )
        )


def scope_id(event) -> str:
    source = event.source
    group_id = getattr(source, "group_id", None)
    room_id = getattr(source, "room_id", None)
    user_id = getattr(source, "user_id", "unknown")
    if group_id:
        return f"group:{group_id}"
    if room_id:
        return f"room:{room_id}"
    return f"user:{user_id}"


def get_display_name(event) -> str:
    source = event.source
    user_id = getattr(source, "user_id", "unknown")
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        try:
            group_id = getattr(source, "group_id", None)
            room_id = getattr(source, "room_id", None)
            if group_id:
                profile = api.get_group_member_profile(group_id, user_id)
            elif room_id:
                profile = api.get_room_member_profile(room_id, user_id)
            else:
                profile = api.get_profile(user_id)
            return profile.display_name or user_id
        except Exception as exc:
            print("profile error:", repr(exc))
            return user_id


def is_admin(display_name: str) -> bool:
    return not ADMIN_LINE_NAMES or display_name in ADMIN_LINE_NAMES


@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event):
    # 依使用者需求：任何圖片都直接開啟新一輪，不分析圖片內容，也不回覆。
    db.start_new_round(scope_id(event))


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event):
    text = (event.message.text or "").strip()
    if not text:
        return

    scope = scope_id(event)
    user_id = getattr(event.source, "user_id", "unknown")
    display_name = get_display_name(event)

    if text in {"統計", "結單"}:
        if not is_admin(display_name):
            return
        reply(event.reply_token, db.summary(scope))
        return

    if text == "我的訂單":
        reply(event.reply_token, db.user_summary(scope, user_id, display_name))
        return

    if text == "清空":
        if is_admin(display_name):
            db.start_new_round(scope)
        return

    if text == "結束":
        if is_admin(display_name):
            db.stop_round(scope)
        return

    if not db.is_active(scope):
        return

    result = ai.parse_chat(
        message=text,
        user_name=display_name,
        current_orders=db.public_orders(scope),
        last_order_user=db.last_order_user_name(scope),
    )
    db.apply_ai_result(
        scope=scope,
        user_id=user_id,
        user_name=display_name,
        result=result,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
