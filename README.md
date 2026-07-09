# LINE AI 訂餐 Bot v4

## 功能
- 貼菜單圖片：Gemini 判斷是否為菜單；新菜單才清空上一輪。
- 非菜單圖片：報表、統計表、照片、聊天截圖直接忽略。
- 平常不回覆任何訊息。
- 只有輸入 `統計` 或 `結單` 才顯示結果。
- 訂餐人永遠是「發訊息的人 LINE Display Name」，不是 @ 標記的人。
- 不是目前菜單品項的內容一律排除。
- 自動忽略：謝謝、共400、OK、Emoji、@某人、URL、電話、地址、測試文字等。

## 統計格式

ANITA :
二寶飯 2
鮭魚飯 1

阿緯 :
雞排飯 1
蝦排飯 1

----------------

二寶飯 2
鮭魚飯 1
雞排飯 1
蝦排飯 1

## Render Environment Variables

必要：
- LINE_CHANNEL_SECRET
- LINE_CHANNEL_ACCESS_TOKEN
- GEMINI_API_KEY

選填：
- ADMIN_LINE_NAMES
  - 例如：ANITA,阿緯
  - 沒填時所有人都能統計/結單。
- ADMIN_ONLY_STATS
  - true：統計與結單都限制管理員。
  - false：只有結單限制管理員，統計所有人可看。
