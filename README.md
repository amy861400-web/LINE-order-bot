# LINE Order Bot v2.0 LTS

- 傳任何圖片開始新一輪，不分析圖片。
- Round 與訂單均存 SQLite。
- 所有人可統計／結單。
- 支援 +、＋、&、x3、X3、×3、*3。
- 支援「我的訂單」「取消我的訂單」「清空」「結束」。

Render 若需跨部署保留 SQLite，請掛載 Persistent Disk，並設定 DB_PATH=/var/data/orders.db。
