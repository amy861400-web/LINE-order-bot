# LINE AI 訂餐 Bot v2

功能：
- 菜單圖片才開始新一輪。
- 非菜單圖片（報表、統計表、對話截圖）忽略。
- 平常聊天不回覆。
- 輸入 `統計` 或 `結單` 才顯示結果。
- 自動抓 LINE 使用者自己的顯示名稱。
- 自動忽略：謝謝、共400、OK、emoji、@某人、測試版等非餐點內容。
- 防止 Gemini 把整份菜單當成訂單。

Render Environment Variables：
- LINE_CHANNEL_SECRET
- LINE_CHANNEL_ACCESS_TOKEN
- GEMINI_API_KEY
- ADMIN_LINE_NAMES（可選，例如：ANITA,阿緯；沒填代表所有人可統計/結單）
