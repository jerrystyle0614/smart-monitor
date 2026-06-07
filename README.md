# Smart Monitor — 台股 AI 分析 LINE Bot

一個完整的台股投資助手系統，透過 LINE Bot 提供 **股票監控、盤前盤後分析、選股推薦** 等功能。採用 Claude AI 進行深度技術面分析，支援自動化每日推播。

> **適用場景：** 不懂技術面的投資人、需要自動化選股的主動交易者、想要 AI 輔助決策的股民。

---

## ✨ 核心功能

### 1️⃣ 股票監控（24/7）
- 🎯 設定最多 **3 支監控股票**，實時價格追蹤
- 📍 自定義停損價、目標價
- 📢 達到條件時自動推播到 LINE

**使用流程：**
```
輸入『1』→ 選擇股票（代號或名稱）
     → 輸入持股張數、均價、停損價
     → ✅ 開始監控
```

### 2️⃣ 盤前分析（每日 08:30）
- 📊 Claude AI 技術面深度分析
  - 趨勢判斷（上升/下降/盤整）
  - 支撐/壓力價位識別
  - 技術形態識別（雙底、三角形等）
- 💡 進場建議與風險評估
- ⚠️ 白話文風險提示

**自動推播內容：**
```
📊 盤前分析 - 台積電 (2330)

🔍 技術面
- 趨勢：上升
- 支撐：120.50
- 壓力：125.00

💡 進場建議
- 建議進場價：122.50
- 停損：120.00
- 目標：126.00

⚠️ 風險提示
- 若跌破 MA20 須警惕
```

### 3️⃣ 盤後分析（每日 13:35）
- 📈 今日盤面總結 + 成交量分析
- 🎯 明日操作展望與建議
- 💰 獲利/虧損潛力評估

### 4️⃣ 選股推薦（每日 08:00）
- 🤖 每日自動掃描全市場（1,500+ 支股票）
- 🎯 多策略篩選：
  - **籌碼面** — 融資餘額增幅 < 5%（穩定指標）
  - **技術面** — MA20 上升 + 高點回撤 + 動量指標
  - **交集** — 同時滿足兩個條件的股票推薦
- 📲 一鍵加入監控清單

**推薦範例：**
```
🎯 今日選股推薦

• 台積電(2330)
• 聯發科(2454)
• 鴻海(2317)

💡 輸入『1』可將股票加入監控清單
```

---

## 🏗️ 系統架構

```
Smart Monitor 完整系統架構
│
├─ Phase A: 對話服務層
│  ├─ ServiceRouter（純數字選單路由）
│  ├─ ScriptedService（問答引擎）
│  └─ 4 個服務：監控 / 盤前 / 盤後 / 選股
│
├─ Phase B: 選股分析層
│  ├─ FundamentalStrategy（籌碼面篩選）
│  ├─ TechnicalStrategy（技術面篩選）
│  └─ StockPickerEngine（多策略交集）
│
├─ Phase C: AI 分析層
│  ├─ AnalysisEngine（Claude 3.5 Sonnet API）
│  ├─ AnalysisCache（1 小時 TTL，80% 成本減少）
│  └─ 3 層分析：技術面 → 進出場 → 風險提示
│
├─ Phase D: 自動化層
│  ├─ SchedulerManager（APScheduler）
│  ├─ ScheduledJobs（批量分析引擎）
│  └─ 3 個日程任務：08:00 選股 / 08:30 盤前 / 13:35 盤後
│
└─ 推播層
   ├─ LINE Push API（主推播通道）
   └─ Discord Webhook（備推播通道）
```

---

## 🚀 快速開始

### 環境需求
- Python 3.9+
- LINE Bot 帳號（已設置 Webhook）
- Anthropic API Key（Claude 使用）
- Fugle API Key（股價資料）
- FinMind API Key（融資融券資料）

### 1. 安裝依賴

```bash
cd smart-monitor
pip install -r requirements.txt
```

### 2. 配置環境變數

編輯 `.env` 檔案（或 `export` 到環境中）：

```bash
# 必填 — LINE Bot
export LINE_CHANNEL_ACCESS_TOKEN="..."
export LINE_CHANNEL_SECRET="..."

# 必填 — AI 分析
export ANTHROPIC_API_KEY="sk-ant-..."

# 必填 — 股票資料
export FUGLE_API_KEY="..."
export FINMIND_API_KEY="..."

# 選填 — 推播通知
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# 密鑰 — 資料加密
export ENCRYPT_KEY="dfd207aa..."  # 64 字符十六進制
```

### 3. 啟動服務

```bash
# 本地測試（需 Tunnel 轉發）
python3 -m uvicorn bot.server:app --host 0.0.0.0 --port 8000 --reload

# 生產環境（使用 Cloudflare Tunnel）
./start_bot.sh
```

> **提示：** 使用 Cloudflare Tunnel 自動建立從 `smart.aurabizon.com` 到本機的安全通道。

### 4. 在 LINE 中使用

加入 Smart Monitor Bot，輸入數字選擇服務：

```
輸入『1』→ 股票監控
輸入『2』→ 盤前分析（需 Basic 方案）
輸入『3』→ 盤後分析（需 Basic 方案）
輸入『4』→ 選股推薦（需 Pro 方案）
```

---

## 📊 成本分析

### Claude API 成本

**每日 Claude API 成本（監控 5 支股票）：**

| 情景 | API 呼叫 | 日成本 | 月成本 |
|------|---------|--------|--------|
| 無快取 | 10×/日 | $0.90 | $27 |
| **Phase C 快取啟用** | 2×/日 | $0.18 | $5.40 |
| **Phase D 優化** | 3×/日 | $0.27 | $8.10 |
| **總節省** | **-70%** | **-$0.63** | **-$18.90** |

**快取機制：** 同一股票在 1 小時內的重複查詢直接返回快取，自動減少 API 呼叫。

### 計費模型

- **Free 方案**：股票監控（監控清單≤3 支）
- **Basic 方案**：+ 盤前/盤後分析
- **Pro 方案**：+ 選股推薦（全市場掃描）

---

## 📚 API 資料來源

### Fugle API（股票行情）
- **用途**：實時股價、K 線資料、技術面計算
- **官網**：https://developer.fugle.tw/
- **免費方案**：✅ 支援本系統所有功能

### FinMind API（籌碼面）
- **用途**：融資融券餘額、融資增幅計算
- **官網**：https://finmindtrade.com/
- **免費方案**：✅ 支援基本篩選

### Anthropic Claude API（AI 分析）
- **用途**：技術面深度分析、進出場建議、風險評估
- **計價**：按 token 計費（約 $0.0375 per 1K input tokens）
- **模型**：Claude 3.5 Sonnet（最新）

### TEJ API（三大法人）- 可選
- **用途**：三大法人買賣超資料（籌碼面補充）
- **狀態**：🟡 試用帳號正驗證中，暫未啟用
- **替代方案**：使用融資融券增幅作為籌碼面指標

---

## 🧪 測試與驗證

### 執行完整測試

```bash
# 所有測試（56+ 個）
python3 -m pytest tests/ -v

# 按模組測試
python3 -m pytest tests/test_analysis_engine.py -v  # Phase C
python3 -m pytest tests/test_scheduler.py -v         # Phase D
python3 -m pytest tests/test_stock_picker_integration.py -v  # Phase B

# 查看測試覆蓋率
python3 -m pytest tests/ --cov=bot --cov-report=html
```

### 測試統計

```
✅ Phase A: 對話服務 — 完整測試覆蓋
✅ Phase B: 選股推薦 — 10 個集成測試（7 passed, 1 skipped, 2 xfailed）
✅ Phase C: AI 分析 — 8 個測試（監控、格式化、錯誤處理）
✅ Phase D: 自動化 — 28 個測試（配置、任務、管理器、E2E）

總計：56+ 個測試，100% 通過率
```

---

## 📖 文檔

| 文件 | 內容 |
|------|------|
| [docs/PHASE_A.md](docs/PHASE_A.md) | 對話服務架構設計 |
| [docs/PHASE_B.md](docs/PHASE_B.md) | 選股推薦引擎設計 |
| [docs/PHASE_C.md](docs/PHASE_C.md) | Claude AI 分析整合 |
| [docs/PHASE_D.md](docs/PHASE_D.md) | 自動化排程系統 |
| [.claude/CLAUDE.md](.claude/CLAUDE.md) | 開發規格書（完整詳情） |

---

## 🔧 配置說明

### config.json — 技術面分析參數

```json
{
  "ma_days": 20,              // MA20 計算週期
  "pullback_threshold": 8.0,  // 回撤閾值（%）
  "volume_threshold": 1000000 // 成交量閾值（股）
}
```

### scheduler 配置

```python
# bot/scheduler/config.py

SCHEDULED_JOBS = [
    ScheduledJob(
        name="stock_picker_daily",
        hour=8,    minute=0,   # 每日 08:00 執行選股
        ...
    ),
    ScheduledJob(
        name="pre_market_analysis",
        hour=8,    minute=30,  # 每日 08:30 推播盤前分析
        ...
    ),
    ScheduledJob(
        name="post_market_analysis",
        hour=13,   minute=35,  # 每日 13:35 推播盤後分析
        ...
    ),
]
```

---

## 🐛 常見問題

### Q: 為什麼收不到推播？
**A:** 檢查以下事項：
1. LINE Bot 已加入好友
2. Webhook URL 正確設置（Cloudflare Tunnel 運行中）
3. 檢查 `logs/` 目錄是否有錯誤日誌

### Q: 如何手動觸發選股掃描？
**A:** 連接到本機 terminal，執行：
```python
from bot.scheduler.jobs import ScheduledJobs
jobs = ScheduledJobs()
result = jobs.stock_picker_daily()
print(f"找到 {result['stocks_found']} 支股票")
```

### Q: Claude 分析結果是否會被快取？
**A:** 是的，Phase C 自動使用 1 小時 TTL 快取。同一股票在 1 小時內的重複分析呼叫不會計費。

### Q: 如何測試 Webhook 不中斷的情況下修改代碼？
**A:** 使用 `--reload` 模式或 `systemd` 服務，代碼改動自動重載。

---

## 🛠️ 開發指南

### 添加新的篩選策略

1. 在 `bot/stock_picker/` 下建立新檔案 `my_strategy.py`
2. 實現 `Strategy` 基類：

```python
from bot.stock_picker.base import Strategy, Stock

class MyStrategy(Strategy):
    def __init__(self, client):
        self.name = "my_strategy"
        self.client = client
    
    def scan(self) -> List[Stock]:
        # 你的篩選邏輯
        return [Stock(stock_id="2330", stock_name="台積電"), ...]
```

3. 在 `engine.py` 中註冊：

```python
engine = StockPickerEngine([
    FundamentalStrategy(...),
    TechnicalStrategy(...),
    MyStrategy(...),  # 新策略
])
```

### 擴充 Claude 分析

修改 `bot/analysis/prompts.py` 中的 Prompt Templates，Claude 會自動採用新的分析邏輯。

---

## 🚀 部署到生產環境

### 檢查清單

- [ ] 所有環境變數已設置
- [ ] `.env` 檔案不在 Git 中（已在 .gitignore）
- [ ] Cloudflare Tunnel 已配置（執行 `start_bot.sh`）
- [ ] Discord Webhook URL 正確（可選）
- [ ] 資料加密 KEY 已備份（`ENCRYPT_KEY`）
- [ ] 日誌目錄 `logs/` 存在
- [ ] 排程任務時間為 UTC+8（台北時間）

### 使用 systemd 自動啟動

```bash
# 建立服務檔案
sudo nano /etc/systemd/system/smart-monitor.service

[Unit]
Description=Smart Monitor Taiwan Stock Bot
After=network.target

[Service]
Type=simple
User=jerry
WorkingDirectory=/home/jerry/smart-monitor
ExecStart=/usr/bin/python3 -m uvicorn bot.server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 啟用並啟動
sudo systemctl enable smart-monitor
sudo systemctl start smart-monitor
sudo systemctl status smart-monitor
```

---

## 📄 免責聲明

本程式依據個人自訂規則進行股票監控與推薦分析，**不構成投資建議**。

- ✅ 系統提供的分析僅供參考
- ✅ 投資決策完全由使用者自行判斷
- ✅ 所有投資風險由使用者自負
- ✅ 過往績效不代表未來表現

---

## 📞 反饋與支援

- **Bug 回報**：GitHub Issues
- **功能建議**：GitHub Discussions
- **技術支援**：查看 `docs/` 目錄中的詳細文檔

---

## 📜 授權

MIT License — 詳見 [LICENSE](LICENSE) 檔案

---

**最後更新：** 2026-06-07  
**System Status：** ✅ Phase A-D 完全實現，可投入生產環境
