# LINE Order Bot v2.1 LTS

## 重點

- 傳任何圖片就開始新一輪，不分析圖片。
- Round 與訂單全部存入 SQLite。
- 前一天傳圖片、隔天早上仍可繼續點餐與統計。
- 即使忘記傳圖片，第一筆有效訂單也會自動建立 Round。
- 所有人都可以輸入 `統計`、`結單`。
- 支援 `我的訂單`、`取消我的訂單`、`清空`、`結束`、`/status`。
- 不使用 Gemini API。

## 支援格式

- `炒麵大x3=150`
- `綜合湯X3=180`
- `雞腿飯×2=210`
- `滷蛋 * 4 = 60`
- `炒麵小+隔間肉湯=100謝謝`
- `炒麵 大 +荷包蛋`

## Render 環境變數

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `DB_PATH`，預設 `data/orders.db`

## 長期保留資料

若要確保 Render 重新部署或重建執行環境後資料仍保留，請掛載 Persistent Disk，並設定：

`DB_PATH=/var/data/orders.db`
