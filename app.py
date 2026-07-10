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

from gemini_ai import GeminiOrderAI
from order_manager import OrderManager


app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "").strip()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

if not LINE_CHANNEL_SECRET:
    raise RuntimeError("缺少環境變數 LINE_CHANNEL_SECRET")
if not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("缺少環境變數 LINE_CHANNEL_ACCESS_TOKEN")

ADMIN_LINE_NAMES = {
    name.strip()
    for name in os.getenv("ADMIN_LINE_NAMES", "").split(",")
    if name.strip()
}

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
orders = OrderManager()
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
        # 回 200，避免 LINE 重複投遞；錯誤留在 Render Logs。
        print("Webhook error:", repr(exc))

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


def source_scope(event) -> str:
    source = event.source
    group_id = getattr(source, "group_id", None)
    room_id = getattr(source, "room_id", None)
    user_id = getattr(source, "user_id", None)
    if group_id:
        return f"group:{group_id}"
    if room_id:
        return f"room:{room_id}"
    return f"user:{user_id or 'unknown'}"


def get_display_name(event) -> str:
    source = event.source
    user_id = getattr(source, "user_id", None)
    if not user_id:
        return "unknown"

    try:
        with ApiClient(configuration) as api_client:
            api = MessagingApi(api_client)
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
        print("Profile error:", repr(exc))
        return user_id


def is_admin(display_name: str) -> bool:
    return not ADMIN_LINE_NAMES or display_name in ADMIN_LINE_NAMES


@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event):
    # 不下載、不辨識圖片。任何圖片都直接開始新一輪。
    scope_id = source_scope(event)
    orders.start_new_round(scope_id)
    print(f"New order round started: {scope_id}")


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event):
    text = (event.message.text or "").strip()
    if not text:
        return

    scope_id = source_scope(event)
    user_id = getattr(event.source, "user_id", None) or "unknown"
    display_name = get_display_name(event)

    if text in {"統計", "結單"}:
        if is_admin(display_name):
            reply(event.reply_token, orders.summary(scope_id))
        return

    if text == "我的訂單":
        reply(event.reply_token, orders.my_order(scope_id, user_id))
        return

    if text == "清空":
        if is_admin(display_name):
            orders.clear(scope_id)
        return

    if text == "結束":
        if is_admin(display_name):
            orders.stop(scope_id)
        return

    # 必須先傳圖片，才會有啟用中的訂餐輪次。
    if not orders.is_active(scope_id):
        return

    result = ai.parse_chat(
        message=text,
        user_name=display_name,
        menu=[],
        current_orders=orders.public_orders(scope_id),
        last_order_user=orders.last_order_user_name,
    )

    orders.apply_ai_result(
        scope_id=scope_id,
        user_id=user_id,
        user_name=display_name,
        result=result,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
