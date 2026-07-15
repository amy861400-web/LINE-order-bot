from __future__ import annotations
import os
from flask import Flask,request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import ApiClient,Configuration,MessagingApi,ReplyMessageRequest,TextMessage
from linebot.v3.webhooks import ImageMessageContent,MessageEvent,TextMessageContent
from order_manager import OrderManager
from parser import OrderParser
app=Flask(__name__)
SECRET=os.getenv('LINE_CHANNEL_SECRET','').strip();TOKEN=os.getenv('LINE_CHANNEL_ACCESS_TOKEN','').strip()
if not SECRET:raise RuntimeError('缺少環境變數 LINE_CHANNEL_SECRET')
if not TOKEN:raise RuntimeError('缺少環境變數 LINE_CHANNEL_ACCESS_TOKEN')
configuration=Configuration(access_token=TOKEN);handler=WebhookHandler(SECRET);orders=OrderManager();parser=OrderParser()
@app.get('/')
def home():return 'LINE Order Bot v2.1 LTS OK',200
@app.post('/callback')
def callback():
    sig=request.headers.get('X-Line-Signature','');body=request.get_data(as_text=True)
    try:handler.handle(body,sig)
    except InvalidSignatureError:return 'Invalid signature',400
    except Exception as e:print('Webhook error:',repr(e))
    return 'OK',200
def reply(token,text):
    with ApiClient(configuration) as c:MessagingApi(c).reply_message(ReplyMessageRequest(reply_token=token,messages=[TextMessage(text=text[:4900])]))
def scope(event):
    s=event.source;g=getattr(s,'group_id',None);r=getattr(s,'room_id',None);u=getattr(s,'user_id',None)
    return f'group:{g}' if g else f'room:{r}' if r else f'user:{u or "unknown"}'
def display(event):
    s=event.source;u=getattr(s,'user_id',None)
    if not u:return 'unknown'
    try:
        with ApiClient(configuration) as c:
            api=MessagingApi(c);g=getattr(s,'group_id',None);r=getattr(s,'room_id',None);p=api.get_group_member_profile(g,u) if g else api.get_room_member_profile(r,u) if r else api.get_profile(u);return p.display_name or u
    except Exception as e:print('Profile error:',repr(e));return u
@handler.add(MessageEvent,message=ImageMessageContent)
def on_image(event):orders.start_new_round(scope(event));print('New round started')
@handler.add(MessageEvent,message=TextMessageContent)
def on_text(event):
    text=(event.message.text or '').strip();sc=scope(event);uid=getattr(event.source,'user_id',None) or 'unknown'
    if not text:return
    if text in {'統計','結單'}:reply(event.reply_token,orders.summary(sc));return
    if text=='我的訂單':reply(event.reply_token,orders.my_order(sc,uid));return
    if text in {'取消我的訂單','取消訂單'}:orders.apply(sc,uid,display(event),{'action':'cancel'});return
    if text=='清空':orders.clear(sc);return
    if text=='結束':orders.close(sc);return
    if text=='/status':reply(event.reply_token,orders.status(sc));return
    result=parser.parse(text)
    if result.get('action')!='ignore':orders.apply(sc,uid,display(event),result)
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')))
