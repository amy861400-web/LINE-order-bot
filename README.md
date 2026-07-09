# LINE AI 訂餐 Bot

## Render Environment Variables
請在 Render → Environment 新增：

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `GEMINI_API_KEY`

## LINE Webhook URL

`https://你的-render網址.onrender.com/callback`

## 使用方式

- 貼菜單圖片：自動清空上一輪，開始新一輪，不回覆。
- 平常聊天：不回覆。
- 輸入 `統計`：回覆今日訂單與餐點統計。
- 輸入 `明細`：只看人員明細。
- 輸入 `結束`：停止記錄，直到下一張菜單圖片。
- 輸入 `清空`：清空目前訂單。

## 注意
免費 Render 服務重啟後，記憶會清空。若要永久保存，之後可加資料庫。
