# LINE Order Bot 正式版 v1.0

功能：
- 貼菜單圖片自動開始新一輪
- 非菜單圖片忽略
- 只允許目前菜單內餐點加入訂單
- @標記不會變成訂餐人，訂餐人永遠是發訊息者 LINE Display Name
- 輸入「統計」或「結單」才回覆

Render Environment Variables：
- LINE_CHANNEL_SECRET
- LINE_CHANNEL_ACCESS_TOKEN
- GEMINI_API_KEY
- ADMIN_LINE_NAMES（選填，例如：ANITA,阿緯）

Render Start Command：
```
gunicorn app:app
```
