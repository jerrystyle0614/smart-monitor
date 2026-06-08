# Smart Monitor — 台股 AI 分析 LINE Bot 開發規格書

你是一位精通台股 API 開發、LINE Bot 架構設計與 AI 整合的資深 Python 工程師。
本文件描述系統現況、已完成功能、進行中設計，以及未來擴充方向。

---

## 一、專案定位

透過 LINE Bot 提供台股投資人四種服務：
1. **股票監控**：設定持股條件，達到停損/目標價時即時推播
2. **盤前分析**：每日 08:30 推播個股技術面分析與進場建議
3. **盤後分析**：每日 13:35 推播個股技術面分析與出場建議
4. **選股推薦**：使用者手動輸入條件（資金、持有期間、風險偏好），系統依條件套用對應策略篩選，AI 選出 5 檔並白話解釋（pro 方案專屬）

目標使用者：**不懂技術面的一般投資人**，系統負責分析，AI 負責用白話解釋。

---

## 二、技術棧（現況）

| 用途 | 選型 | 說明 |
|------|------|------|
| 語言 | Python 3.9 | 注意：不可使用 `X \| Y` 型別語法，需用 `Optional[X]` |
| LINE Bot | `line-bot-sdk` v3 | Messaging API，Webhook 接收訊息 |
| 台股即時報價 | Fugle REST API | `intraday/quote`，免費方案 |
| 台股日K | Fugle REST API | `historical/candles`，免費方案 |
| 股票名稱驗證 | Fugle REST API | 用代號查名稱，確保正確性 |
| 籌碼面資料 | FinMind API | 三大法人買賣超（選股推薦用） |
| 意圖判斷 | ~~Gemini API~~ | **Phase A 已移除，改為純數字選單** |
| 欄位解析 | ~~Gemini API~~ | **Phase A 已移除，改為問答腳本引導** |
| AI 分析 | Claude API | 個股波段白話解釋、選股推薦（從候選股選 5 檔並說明） |
| 推播通知 | LINE push + Discord Webhook | 雙管道同步推播 |
| Tunnel | Cloudflare Tunnel | 固定網址 smart.aurabizon.com |
| Web Server | FastAPI + uvicorn | PORT 8000 |

---

## 三、現有檔案結構（已完成）

```
smart-monitor/
├── bot/
│   ├── server.py          # FastAPI webhook server，lifespan 管理
│   ├── handlers.py        # 訊息路由（待 Phase A 重寫）
│   ├── state_machine.py   # 對話狀態機（待 Phase A 重寫）
│   ├── user_store.py      # 使用者資料讀寫（JSON 檔案）
│   ├── line_client.py     # LINE push/reply 封裝
│   ├── claude_parser.py   # Fugle 股票清單載入、股票代號驗證
│   ├── monitor_engine.py  # 背景監控引擎（30秒輪詢、交易時段判斷）
│   └── analysis_runner.py # 個股波段分析執行與格式化
├── notifier.py            # Discord Webhook 推播
├── daily_data.py          # Fugle 日K抓取
├── swing_strategy.py      # MA20 + 高點回撤波段分析
├── strategy.py            # Alert 資料類別
├── config.json            # 波段分析參數設定
├── requirements.txt
└── start_bot.sh           # 啟動腳本（含 Cloudflare Tunnel）
```

---

## 四、Phase A 設計（進行中）

### 目標
用純數字選單 + 問答腳本引擎取代現有的自然語言解析流程，
解決 Gemini 誤判問題，並建立可擴充的服務框架。

### 新檔案結構（Phase A 完成後）

```
smart-monitor/
├── bot/
│   ├── server.py              # 不動
│   ├── router.py              # ServiceRouter，取代 handlers.py
│   ├── user_store.py          # 擴充服務狀態欄位
│   ├── line_client.py         # 不動
│   ├── monitor_engine.py      # 不動（背景監控保留）
│   ├── analysis_runner.py     # 不動
│   │
│   ├── services/              # 各服務模組（新建）
│   │   ├── __init__.py
│   │   ├── base.py            # ScriptedService 問答腳本基底類別
│   │   ├── stock_monitor.py   # 股票監控服務腳本
│   │   ├── pre_market.py      # 盤前分析服務腳本
│   │   └── post_market.py     # 盤後分析服務腳本
│   │
│   └── data/                  # 資料來源模組（新建，整合分散的 Fugle 呼叫）
│       └── fugle_client.py    # Fugle API 統一封裝
│
├── claude_parser.py           # 保留 load_stock_map、_verify_stock
├── notifier.py                # 不動
├── daily_data.py              # 不動
├── swing_strategy.py          # 不動
└── ...
```

### 對話流程

```
使用者輸入任何訊息
        │
        ▼
    ServiceRouter
        │
        ├── 問答進行中 ──────────► 交給目前服務的腳本處理
        │                         合法 → 下一題
        │                         非法 → 重問 + 提示格式
        │                         「取消」→ 回到選單
        │
        └── 其他 ────────────────► 顯示服務選單

服務選單：
━━━━━━━━━━━━━━━━━━
📊 Smart Monitor 服務選單

1️⃣ 股票監控
2️⃣ 盤前分析
3️⃣ 盤後分析
4️⃣ 選股推薦（pro 專屬）

輸入數字選擇服務
━━━━━━━━━━━━━━━━━━
```

### 股票監控問答腳本（4 題）

```
Step 1: 「請問你要監控哪支股票？（輸入名稱或代號）」
        驗證：Fugle API 確認股票存在
        失敗：「找不到此股票，請重新輸入」

Step 2: 「請問持有幾張？」
        驗證：正整數

Step 3: 「請問買入均價是多少元？」
        驗證：正數

Step 4: 「請問停損價是多少元？（輸入『跳過』略過）」
        驗證：正數 或 「跳過」

完成 → 顯示確認卡片 → 使用者確認 → 進入監控
```

### ScriptedService 基底設計

```python
class ScriptedService:
    name: str               # 服務名稱
    steps: list[Step]       # 問答步驟列表

class Step:
    field: str              # 儲存欄位名稱
    question: str           # 問題文字
    validate: Callable      # 驗證函式，回傳 (ok: bool, value, error_msg: str)
    optional: bool = False  # 是否可跳過
```

---

## 五、選股推薦服務（已實作）

實作於 `bot/services/stock_picker.py`，為**手動觸發**的條件式選股，
**非**自動掃描推播。使用者從選單選「4️⃣ 選股推薦」進入三步問答，
系統依條件選股後只推播給該使用者。pro 方案專屬。

> 注意：`bot/stock_picker/` 下的 `engine.py`、`scheduler.py` 為早期「每日 08:00 自動掃描推播」
> 的舊架構，目前未啟用（`SchedulerManager` 雖保留 `stock_picker_daily` 入口，但 engine 傳 None 空轉）。
> 實際運作的選股邏輯在 `bot/services/stock_picker.py`。

### 問答腳本（3 題）

```
Step 1: 「你目前有多少資金可以投入？（元）」
        驗證：正數

Step 2: 「你希望持有多久？」
        1️⃣ 短期（1～4 週）  2️⃣ 中期（1～3 個月）  3️⃣ 長期 / 定期定額
        驗證：1、2 或 3

Step 3: 「你對虧損的接受度？」
        1️⃣ 保守（最多虧 5%）  2️⃣ 穩健（最多虧 10～15%）  3️⃣ 積極
        驗證：1、2 或 3
```

### 選股流程

```
三題收齊
   │
   ▼
依（持有期 + 風險偏好）對應出技術面策略
   （aggressive_short / momentum_mid / defensive_band /
     high_yield_stable / dca_stable）
   │
   ▼
掃描預設股票池（_SCAN_UNIVERSE，約 30 檔，涵蓋權值股/ETF/中型科技/低價股）
   ├── 技術面：MA20 方向、收盤位置、量比、回撤，依策略調整嚴格度
   └── 籌碼面：FinMind 三大法人近 5 日淨買超（積極/動能策略要求淨買超）
   │
   ▼
Claude（haiku）從候選股選出最適合的 5 檔 + 策略名稱 + 各檔推薦理由（回 JSON）
   │
   ▼
格式化推播給該使用者（含可否買整張 / 零股提示）
```

### 限制與快取

- **每日查詢上限**：每位使用者 10 次（`MAX_DAILY_QUERIES`），存於 `users/{uid}/picker_queries.json`
- **當日快取**：以（日期 + 風險 + 持有期 + 資金級距）為 key 快取選股結果於 `cache/stock_picker/`，命中則直接回覆（仍計入查詢次數）

---

## 六、未來 Phase 規劃

### Phase C：AI 分析升級

- 監控服務：Claude 分析主力動向（技術面），判斷進出場時機
- 盤前分析：Claude 分析個股是否適合今日操作
- 盤後分析：Claude 分析建議進出場價格水位、獲利空間、風險控管

---

## 七、環境變數

| 變數 | 用途 |
|------|------|
| `FUGLE_API_KEY` | Fugle REST API 金鑰 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot 推播 token |
| `LINE_CHANNEL_SECRET` | LINE Webhook 簽章驗證 |
| `ANTHROPIC_API_KEY` | Claude API（個股白話解釋、選股推薦） |
| `FINMIND_API_KEY` | FinMind API 金鑰（選股籌碼面資料） |
| `DISCORD_WEBHOOK_URL` | Discord 推播 |
| `GEMINI_API_KEY` | Gemini API（Phase A 暫不使用） |
| `CLEAR_ON_START` | `=1` 時啟動清空使用者資料（測試用） |
| `FORCE_TRADING_HOURS` | `=1` 時強制視為交易時段（測試用） |

---

## 八、開發守則

1. Python 3.9 相容：不用 `X | Y`、`list[str]`（類型提示用 `Optional`、`List`）
2. 所有網路呼叫加 try-except，失敗只印警告，不崩潰
3. 使用者資料存在 `users/{line_user_id}/` 下的 JSON 檔案
4. 推播一律 LINE push + Discord 雙管道
5. 交易時段判斷：週一到週五 09:00–13:30 UTC+8
6. 分析推播時間：08:30 盤前、13:35 盤後
7. 不使用任何 UI 套件，完全終端機操作
