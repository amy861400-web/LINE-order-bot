from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage, MessageEvent, TextMessage
from linebot.exceptions import InvalidSignatureError
import os

app = Flask(__name__)

# LINE 設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


# 測試首頁
@app.route("/")
def home():
    return "LINE Bot OK"


# LINE Webhook
@app.route("/callback", methods=["POST"])
def callback():

    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)

    except InvalidSignatureError:
        return "Invalid signature", 400

    return "OK", 200


# 收到文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):

    text = event.message.text

    reply_text = "收到：" + text

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )


# 啟動
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
