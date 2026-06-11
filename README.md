# Smart Monitor — 台股 AI 分析助理

透過 **LINE Bot** 與 **Telegram Bot** 雙平台，提供台股投資人股票監控、盤前盤後分析、選股推薦等服務。採用 Claude AI 進行技術面分析，支援自動化每日推播。

> **適用對象：** 不懂技術面的一般投資人，系統負責分析，AI 負責用白話解釋。

---

## 功能總覽

| 功能 | 說明 | 方案 |
|------|------|------|
| 股票監控 | 設定停損/目標價，達到條件即時推播 | Free+ |
| 盤前分析 | 每日 08:50 推播技術面分析與進場建議 | Basic+ |
| 盤後分析 | 每日 13:35 推播技術面分析與出場建議 | Basic+ |
| 選股推薦 | 手動觸發，AI 從市場篩選 5 檔並說明 | Pro |
| ETF 推薦 | 手動觸發，依投資目標篩選 ETF | Pro |

---

## 系統架構

```
smart-monitor/
├── bot/
│   ├── server.py              # FastAPI app，lifespan 管理
│   ├── router.py              # ServiceRouter，訊息路由
│   ├── user_store.py          # 使用者資料（users/line/ / users/telegram/）
│   ├── monitor_engine.py      # 背景監控引擎（30秒輪詢，多平台）
│   ├── analysis_runner.py     # 個股分析執行
│   │
│   ├── line/                  # LINE 平台模組
│   │   ├── client.py          # LineClient（push / reply）
│   │   └── webhook.py         # LINE Webhook 路由
│   │
│   ├── telegram/              # Telegram 平台模組
│   │   ├── client.py          # TelegramClient（push / reply / send_menu）
│   │   ├── webhook.py         # Telegram Webhook 路由
│   │   ├── keyboard.py        # Inline Keyboard 產生器
│   │   └── invite.py          # 邀請碼管理
│   │
│   ├── services/              # 各服務問答腳本
│   │   ├── base.py            # ScriptedService 基底
│   │   ├── stock_monitor.py   # 股票監控
│   │   ├── pre_market.py      # 盤前分析
│   │   ├── post_market.py     # 盤後分析
│   │   ├── stock_picker.py    # 選股推薦
│   │   └── etf_picker.py      # ETF 推薦
│   │
│   ├── analysis/              # Claude AI 分析層
│   │   ├── engine.py          # AnalysisEngine
│   │   ├── prompts.py         # Prompt Templates
│   │   └── cache.py           # 分析結果快取
│   │
│   ├── data/                  # 資料來源封裝
│   │   ├── fugle_client.py    # Fugle API（即時報價）
│   │   ├── institutional_client.py  # FinMind 三大法人
│   │   └── market_context.py  # 大盤背景資料
│   │
│   └── scheduler/             # 排程管理
│       ├── manager.py         # SchedulerManager（APScheduler）
│       ├── jobs.py            # 排程任務定義
│       └── config.py          # 排程時間設定
│
├── notifier.py                # Discord Webhook 推播
├── daily_data.py              # Fugle 歷史日K 抓取（舊版，部分模組仍使用）
├── market_data.py             # 行情來源封裝（MockMarketData / RealMarketData）
├── strategy.py                # Alert 資料類別與警報條件判斷
├── swing_strategy.py          # MA20 + 高點回撤波段分析
├── analyze.py                 # 手動觸發盤前/盤後分析入口
├── main.py                    # 舊版主程式入口（已由 bot/server.py 取代）
├── mock_stocks.py             # 測試用模擬股票資料
├── set_invite.py              # 產生 Telegram 邀請碼 CLI
├── set_user_plan.py           # 手動設定使用者方案 CLI
├── migrate_users.py           # 一次性資料遷移腳本（users/ → users/line/）
├── data/
│   └── invites.json           # Telegram 邀請碼儲存
└── users/
    ├── line/                  # LINE 使用者資料
    └── telegram/              # Telegram 使用者資料
```

---

## 推播平台

### LINE Bot
- 訊息式問答流程（純文字選單）
- 免費方案每月 500 則 push 上限
- Webhook：`https://smart.aurabizon.com/webhook`

### Telegram Bot
- Inline Keyboard 按鈕互動
- 邀請碼制，需由管理員發放才能使用
- 無推播數量限制
- Webhook：`https://smart.aurabizon.com/telegram/webhook`

**Telegram 按鈕行為：**

| 情境 | 顯示按鈕 |
|------|----------|
| 主選單 | 1️⃣–5️⃣ 服務選擇 |
| 一般問答步驟 | ❌ 取消 |
| 可選步驟（如停損價） | ⏭ 跳過 ＋ ❌ 取消 |
| 確認監控條件 | ✅ 確認 ＋ ❌ 取消 |

---

## 快速開始

### 環境需求

- Python 3.9+
- Fugle API Key（即時報價）
- Anthropic API Key（Claude AI 分析）
- FinMind API Key（三大法人資料）
- LINE Bot 或 Telegram Bot Token

### 安裝

```bash
pip install -r requirements.txt
```

### 環境變數（.env）

```bash
# 股票資料
FUGLE_API_KEY=...
FINMIND_API_KEY=...

# AI 分析
ANTHROPIC_API_KEY=sk-ant-...

# LINE Bot
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_CHANNEL_SECRET=...

# Telegram Bot
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://smart.aurabizon.com/telegram/webhook

# 推播
DISCORD_WEBHOOK_URL=...
DISCORD_ERROR_WEBHOOK_URL=...   # Server 500 錯誤專用頻道

# 資料加密
ENCRYPT_KEY=...   # 64 字元 hex

# 測試用
FORCE_TRADING_HOURS=1   # 強制視為交易時段
```

### 啟動

```bash
# 開發模式
python3 -m uvicorn bot.server:app --port 8000 --reload

# 生產環境（launchd 自動管理）
launchctl load ~/Library/LaunchAgents/com.smartmonitor.bot.plist
```

### 產生 Telegram 邀請碼

```bash
python3 set_invite.py --plan pro --count 1
# 輸出：SMX9Y2
```

---

## 排程任務

| 任務 | 時間（UTC+8） | 說明 |
|------|--------------|------|
| 盤前分析推播 | 08:50 | 對所有監控使用者推播盤前分析 |
| 盤後分析推播 | 13:35 | 對所有監控使用者推播盤後分析 |

> 歷史日K 全面改用 **yfinance** 抓取，Fugle API 僅保留即時報價，避免 429 限流。

---

## 資料來源

| 用途 | 來源 |
|------|------|
| 即時報價 | Fugle REST API |
| 歷史日K | yfinance（`{stock_id}.TW`） |
| 三大法人 | FinMind API |
| AI 分析 | Anthropic Claude API（claude-haiku-4-5） |

---

## 測試

```bash
python3 -m pytest tests/ -q
# 189 passed
```

---

## 環境監控

- Server 崩潰自動重啟：launchd `KeepAlive=true`，`ThrottleInterval=10s`
- 500 錯誤：自動推播 stack trace 到 Discord Error 頻道
- Log：`/tmp/smartmonitor-bot.log` / `/tmp/smartmonitor-bot-err.log`

---

## 使用者資料結構

```
users/
├── line/{line_user_id}/
│   ├── profile.json     # plan, created_at
│   ├── state.json       # 對話狀態、草稿
│   └── watchlist.json   # 監控清單（敏感欄位加密）
└── telegram/{chat_id}/
    ├── profile.json
    ├── state.json
    └── watchlist.json
```

敏感欄位（持股數、均價、停損價）使用 `ENCRYPT_KEY` AES 加密儲存。

---

## Changelog

### 2026-06-11 — Telegram Bot 整合
- 新增 `bot/telegram/` 模組：TelegramClient、Inline Keyboard、webhook、邀請碼
- Telegram 按鈕自動偵測訊息內容並附上對應 keyboard（主選單／確認／跳過）
- 邀請碼系統：`set_invite.py` CLI，新使用者需邀請碼啟用服務
- MonitorEngine 支援多平台 stores/clients dict，兩平台同時監控推播
- UserStore 資料路徑分離：`users/line/` 與 `users/telegram/` 獨立儲存
- LINE 模組重構：`bot/line_client.py` → `bot/line/client.py` + `bot/line/webhook.py`

### 2026-06-07 — 穩定性與 AI 修正
- 盤前推播時間修正：觸發時間改為 08:50，修正 PREMARKET 模式判斷錯誤
- AI 進場價修正：Prompt 加入約束，禁止建議高於現價的追高價
- 歷史日K 全面改用 yfinance，解決 Fugle 429 限流問題
- Server 500 錯誤自動推播 stack trace 到 Discord 專屬錯誤頻道
- launchd 自動重啟機制，崩潰後 10 秒重啟

---

## 免責聲明

本系統提供的分析內容**不構成投資建議**，所有投資決策及風險由使用者自行承擔。
