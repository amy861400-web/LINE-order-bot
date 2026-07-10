# LINE AI 訂餐 Bot

## 使用方式

1. 群組傳送任何圖片：清空上一輪並開始新一輪，Bot 不回覆。
2. 大家用自然語言點餐，Bot 平常不回覆。
3. 輸入 `統計` 或 `結單` 顯示結果。
4. 輸入 `我的訂單` 查看自己的訂單。
5. 管理員可用 `清空`、`結束`。

一般點餐會累加；只有明確輸入「改／換」才會覆蓋自己的舊訂單。

## Render 環境變數

必填：

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `GEMINI_API_KEY`

選填：

- `ADMIN_LINE_NAMES`：逗號分隔，例如 `ANITA,阿緯`。未設定時所有人都可統計、結單、清空、結束。
- `GEMINI_MODEL`：預設 `gemini-2.0-flash`。
- `DB_PATH`：預設 `orders.db`。

## LINE Webhook

設定：

`https://你的-render-網址.onrender.com/callback`

並開啟 Use webhook、關閉 LINE 官方自動回覆。

## SQLite 注意事項

本專案用 SQLite 儲存訂單。Render 免費 Web Service 的本機檔案可能在重新建立實例或重新部署後消失。若需要真正持久保存，請在 Render 掛載 Persistent Disk，並把 `DB_PATH` 設為掛載路徑，例如：

`/var/data/orders.db`

若只需要當天訂餐，沒有 Persistent Disk 也能運作，但部署或服務重建後資料可能消失。
