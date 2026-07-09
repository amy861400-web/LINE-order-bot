# LINE AI 訂餐 Bot

功能：
- 貼菜單圖片：Gemini 判斷是否為菜單，是菜單才開始新一輪；統計表、報表、非菜單圖片會忽略。
- 自動抓對方自己的 LINE 顯示名稱。
- 平常不回覆任何訊息。
- 只有輸入「統計」或「結單」才顯示結果。
- 忽略「共400」「謝謝」「OK」「emoji」等非餐點內容。
- 統計不顯示金額。

Render Environment Variables：
- LINE_CHANNEL_SECRET
- LINE_CHANNEL_ACCESS_TOKEN
- GEMINI_API_KEY
- ADMIN_LINE_NAMES（選填，例如：ANITA,阿緯；未設定時所有人都可結單）

輸出格式：

ANITA :
二寶飯 2
鮭魚飯 1
辣雞排飯 1

阿緯 :
雞排飯 1
蝦排飯 1

----------------

二寶飯 2
鮭魚飯 1
辣雞排飯 1
雞排飯 1
蝦排飯 1
