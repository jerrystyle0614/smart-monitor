# 3312 弘憶即時盤面監控程式（Fugle 版）

監控台股 3312 弘憶，在指定條件達成時透過 Discord Webhook 發送即時警報。
引入美股（NVDA、SMCI）與台股同業、集團股連動邏輯，動態調整防守策略。

---

## 安裝

```bash
pip install -r requirements.txt
```

---

## 環境變數設定

```bash
export FUGLE_API_KEY="你的富果 API 金鑰"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

未設定 `DISCORD_WEBHOOK_URL` 時，警報直接印在終端機（方便測試）。

---

## 富果 API 金鑰取得

1. 前往 [fugle.tw](https://fugle.tw) 免費註冊會員
2. 進入開發者頁面申請行情 API 金鑰
3. **不需要開券商帳號**，免費方案即可使用

---

## Discord Webhook 取得

1. 在 Discord 伺服器中，進入目標頻道的設定
2. 選擇「整合」→「Webhook」→「建立 Webhook」
3. 複製 Webhook URL 貼入環境變數

---

## 執行指令

```bash
# 模擬模式（不需任何帳號，可立即測試）
python3 main.py --mock

# 真實模式（每次開新終端機都需先 source）
source .env
python3 main.py
```

---

## 訂閱數說明

富果免費方案 WebSocket 上限為 **5 訂閱數**。

本程式訂閱：
- 3312 弘憶 × aggregates
- 2465 麗臺 × aggregates
- 3550 聯穎 × aggregates
- 5471 松翰 × aggregates

共 **4 個訂閱數**，剛好在免費方案限制內。

> ⚠️ 請勿自行增加訂閱其他 channel，否則會超量報錯。

---

## 部署提醒

程式需在盤中持續執行。建議：
- 常開的個人電腦或 NAS
- 雲端 VM（AWS EC2、GCP Compute Engine 等）
- 設定 `systemd` 或 `screen` 確保程序不中斷

---

## 上線前三項必確認

1. **確認 4 檔股票可正常訂閱**
   富果 WebSocket 需確認 3312、2465、3550、5471 均有支援即時行情。

2. **注意 `stop_loss_tightened` 低於成本的邏輯矛盾**
   預設設定：`stop_loss_tightened = 64.5`，而 `cost_price = 64.86`。
   美股利空觸發後，若觸碰防守線將是**小賠出場**。
   請自行決定是否在 `config.json` 中調高 `stop_loss_tightened`。

3. **盤前盤後沒有推播屬正常**
   台股 WebSocket 僅在開盤時間（09:00–13:30）有報價推播，
   盤前盤後 heartbeat 顯示的是上一次收到的數值。

---

## 免責聲明

本程式依使用者自訂規則發送提醒，不預測股價，不構成投資建議。
投資決策請自行判斷，風險自負。
