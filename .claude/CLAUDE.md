# 3312 弘憶即時盤面監控程式 — 開發規格書（Fugle 版）

你是一位精通台股 API 開發與自動化監控的資深 Python 工程師。
請依照以下完整規格，在當前目錄從零建立這個專案。
不需要任何 UI，完全透過終端機操作。

---

## 一、專案目標

監控台股 3312 弘憶（持股 5 張、均價 64.86 元），
在指定條件達成時透過 Discord Webhook 發送即時警報，協助研判出場時機。
同時引入美股（NVDA、SMCI）與台股同業、集團股的連動邏輯，動態調整防守策略。

---

## 二、技術棧

| 用途 | 選型 | 說明 |
|------|------|------|
| 語言 | Python 3.10+ | 型別提示可用 |
| 台股即時行情 | `fugle-marketdata`（富果行情 API） | WebSocket push，`aggregates` channel |
| 美股前夜收盤 | `yfinance` | 啟動時抓一次，盤中靜態 |
| 警報推播 | Discord Webhook（`requests`） | 取代已於 2025/03/31 停用的 LINE Notify |

> ⚠️ LINE Notify 已於 2025/03/31 永久停服，請勿使用。

---

## 三、檔案結構

```
stock_monitor/
├── config.json          # 所有可調整參數，不放任何密鑰
├── requirements.txt
├── notifier.py          # Discord 推播模組
├── market_data.py       # 行情來源（真實 Fugle / 模擬兩種模式）
├── strategy.py          # 連動雷達 + 出場指令判斷
├── main.py              # 主程式、主迴圈、Ctrl+C 優雅退出
└── README.md
```

---

## 四、config.json 規格

```json
{
  "stock_id": "3312",
  "stock_name": "弘憶",
  "total_shares": 5000,
  "cost_price": 64.86,
  "target_stage_1": 75.0,
  "target_stage_2": 85.0,
  "stop_loss_moving": 63.0,
  "stop_loss_tightened": 64.5,
  "alert_volume_threshold": 7000,
  "large_order_lots": 50,
  "peer_stocks": { "2465": "麗臺", "3550": "聯穎" },
  "group_stocks": { "5471": "松翰" },
  "us_tickers": ["NVDA", "SMCI"],
  "us_drop_threshold_pct": 4.0,
  "peer_drop_threshold_pct": 5.0,
  "group_drop_threshold_pct": 4.0,
  "eval_interval_sec": 5
}
```

**config.json 不放任何密鑰。** 敏感資訊一律從環境變數讀取：

| 環境變數 | 說明 |
|----------|------|
| `FUGLE_API_KEY` | 富果行情 API 金鑰（免費方案即可） |
| `DISCORD_WEBHOOK_URL` | Discord 頻道 Webhook URL |

---

## 五、requirements.txt

```
fugle-marketdata>=0.5
yfinance>=0.2
requests>=2.31
```

---

## 六、notifier.py 規格

### 類別：`DiscordNotifier`

```python
class DiscordNotifier:
    def __init__(self, webhook_url: str | None = None): ...
    def send(self, title: str, message: str, color: int = 0x3498DB) -> None: ...
```

### 模組頂層色碼常數

```python
COLOR_INFO   = 0x95A5A6  # 灰：純資訊
COLOR_GREEN  = 0x2ECC71  # 綠：獲利出場
COLOR_YELLOW = 0xF1C40F  # 黃：連動警示
COLOR_RED    = 0xE74C3C  # 紅：停損 / 利空
```

### 行為要求

1. `__init__` 優先讀環境變數 `DISCORD_WEBHOOK_URL`，其次才用傳入的參數。
   若最終仍為空，設 `self.enabled = False`。

2. `send()` 邏輯：
   - `enabled = True`：POST 到 Discord Webhook，用 **embed 格式**。
     embed 包含 `title`（前加 📢）、`description`（message）、
     `color`（左側色條）、`footer`（當下時間戳）。
     HTTP timeout=10，非 200/204 只印警告，不 raise。
   - `enabled = False`：用格式化分隔線 + 標題 + 內容直接 `print` 到終端機，
     讓沒設 webhook 時也能看到完整警報（測試很方便）。

3. 所有例外（網路錯誤等）用 try-except 捕捉後印警告，不讓主程式崩潰。

---

## 七、market_data.py 規格

### 快照統一格式（`snapshot()` 的回傳值）

```python
{
    "target": {
        "price": float | None,       # 3312 最新成交價
        "total_volume": int,         # 當日累計成交量（張）
        "limit_up": float | None,    # 漲停價（由 referencePrice × 1.1 計算）
        "limit_up_opened": bool,     # 是否曾鎖漲停後又被打開
        "last_large_order": int,     # 最近一筆成交的單筆量（張），用於大單偵測
    },
    "peers": {
        "2465": {"name": "麗臺", "price": float, "pct": float},
        "3550": {"name": "聯穎", "price": float, "pct": float},
    },
    "group": {
        "5471": {"name": "松翰", "price": float, "pct": float},
    },
    "us": {
        "NVDA": float,   # 前一晚收盤漲跌幅 %
        "SMCI": float,
    },
}
```

---

### MockMarketData（`--mock` 模式）

不需任何帳號，用隨機漫步模擬盤面，讓你先把「策略邏輯 + Discord 推播」整條流程跑通。

- 3312 價格從 `cost_price` 開始，每次 `snapshot()` 小幅隨機漂移（±0.6）。
- 漲停價固定為 `round(cost_price * 1.1, 2)`。
- 同業、集團的 `pct` 每次隨機累積漂移，讓它最終能超過門檻觸發警示。
- 美股漲跌幅在 `__init__` 以 `random.uniform(-6, 3)` 隨機決定，執行期間固定。
- 漲停打開邏輯：曾觸漲停後跌破就設 `limit_up_opened = True`。
- 大單：約 20% 機率產生 55 或 120 張的大單，其餘 0。
- `start()` 印一行提示說這是模擬模式。
- `stop()` 什麼都不做。

---

### RealMarketData（富果 Fugle 即時模式）

#### 重要前提

富果免費方案 WebSocket 上限是 **5 訂閱數**。
4 檔股票各訂 1 個 `aggregates` channel = 4 訂閱數，剛好在限制內，不要訂其他 channel。

#### `aggregates` channel 推播的資料欄位（接收 JSON message）

```json
{
  "event": "data",
  "channel": "aggregates",
  "data": {
    "symbol": "3312",
    "referencePrice": 65.0,
    "changePercent": 2.5,
    "lastPrice": 66.5,
    "lastSize": 120,
    "bids": [{"price": 66.0, "size": 500}, ...],
    "asks": [{"price": 67.0, "size": 200}, ...],
    "total": {
      "tradeVolume": 3500
    }
  }
}
```

欄位對應說明：
- `lastPrice` → 最新成交價
- `total.tradeVolume` → 當日累計成交量（張）
- `changePercent` → 當日漲跌幅（%），同業/集團股直接用這個
- `lastSize` → 最近一筆成交的單筆量（張），用於大單偵測
- `referencePrice` → 昨日收盤價，用來計算漲停價
- `bids` / `asks` → 五檔買賣（資料有抓但本版策略邏輯不直接用，有就好）

#### `start()` 方法流程

1. 從環境變數讀 `FUGLE_API_KEY`，缺少就 raise RuntimeError 並提示改用 `--mock`。
2. 建立 `WebSocketClient(api_key=api_key)`。
3. 取得 `stock = client.stock`。
4. 用 `stock.on('message', self._handle_message)` 註冊訊息回呼。
5. 用 `stock.on('disconnect', self._handle_disconnect)` 註冊斷線回呼：
   斷線時印警告，5 秒後嘗試重連（呼叫 `stock.connect()` 再重新訂閱）。
6. 用 `stock.on('error', self._handle_error)` 註冊錯誤回呼：只印錯誤，不崩潰。
7. 呼叫 `stock.connect()`。
8. 對所有追蹤股票（3312、2465、3550、5471）各自呼叫：
   `stock.subscribe({'channel': 'aggregates', 'symbol': code})`
9. 呼叫 `self._fetch_us_overnight()`。

#### `_handle_message(message)` 方法

```python
def _handle_message(self, message):
    # message 是 JSON 字串，先 json.loads
    # 只處理 event == "data" 且 channel == "aggregates" 的訊息
    # 用 threading.Lock 保護 self._snap（回呼跑在 WebSocket 的 IO 執行緒）
    # 解析 data 欄位，依 symbol 更新對應的 target / peers / group
```

具體更新邏輯：

**target（3312）**
```python
price  = data["lastPrice"]
vol    = data["total"]["tradeVolume"]
single = data["lastSize"]        # 單筆量

# 漲停價：第一次收到 referencePrice 時計算並快取
if self._snap["target"]["limit_up"] is None:
    ref = data["referencePrice"]
    self._snap["target"]["limit_up"] = round(ref * 1.1, 2)

limit_up = self._snap["target"]["limit_up"]

# 漲停打開偵測
if price >= limit_up:
    self._snap["target"]["_touched"] = True
if self._snap["target"].get("_touched") and price < limit_up:
    self._snap["target"]["limit_up_opened"] = True

self._snap["target"]["price"]             = price
self._snap["target"]["total_volume"]      = int(vol)
self._snap["target"]["last_large_order"]  = int(single)
```

**peers（2465、3550）和 group（5471）**
```python
self._snap["peers"][symbol] = {
    "name": cfg["peer_stocks"][symbol],
    "price": data["lastPrice"],
    "pct":   data["changePercent"],
}
# group 同理
```

#### `_fetch_us_overnight()` 方法

```python
for ticker in config["us_tickers"]:
    hist = yf.Ticker(ticker).history(period="5d")
    if len(hist) >= 2:
        last = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        us[ticker] = round((last - prev) / prev * 100, 2)
```

失敗只印警告，不影響台股監控繼續跑。

#### `snapshot()` 方法

加鎖後 return `copy.deepcopy(self._snap)`。

#### `stop()` 方法

嘗試呼叫 `stock.disconnect()`（或對應的中斷連線方法），try-except 包住。

---

### 工廠函式

```python
def build_market_data(config: dict, use_mock: bool) -> MockMarketData | RealMarketData:
    return MockMarketData(config) if use_mock else RealMarketData(config)
```

---

## 八、strategy.py 規格

### Alert 資料類別

```python
class Alert:
    def __init__(self, title: str, message: str, color: int): ...
```

### StrategyEngine

```python
class StrategyEngine:
    def __init__(self, config: dict): ...
    def evaluate(self, snap: dict) -> list[Alert]: ...
    def _build_body(self, snap: dict, action: str) -> str: ...
```

#### 初始狀態

```python
self.fired = {
    "watch":    False,   # 指令一：開盤看戲（一次性）
    "stage1":   False,   # 指令二：保本落袋 2 張（一次性）
    "stage2":   False,   # 指令三：清倉（一次性）
    "stop":     False,   # 指令四：停損（一次性）
    "us_alert": False,   # 美股利空鎖緊防守線（一次性）
}
self.warned_peers  = set()   # 已警示過的同業 code
self.warned_group  = set()   # 已警示過的集團股 code
self.current_stop  = config["stop_loss_moving"]   # 動態防守線，初始為 63.0
```

#### evaluate() 判斷流程（依序執行）

若 `snap["target"]["price"]` 為 None，直接 return `[]`。

**判斷 1：美股利空 → 動態鎖緊防守線**
```
條件：us 中有任一 ticker 的 pct <= -us_drop_threshold_pct
      且 fired["us_alert"] == False
動作：fired["us_alert"] = True
      self.current_stop = config["stop_loss_tightened"]
      Alert(title="美股 AI 巨頭重挫，防守線鎖緊",
            message=列出哪幾隻跌幅多少、防守線由 63.0 調整到 64.5 及警示說明,
            color=COLOR_RED)
```

**判斷 2：台股同業重挫聯動**
```
條件：peers 中有 code 不在 warned_peers 且 pct <= -peer_drop_threshold_pct
動作：warned_peers.add(code)
      Alert(title="算力同業出現賣壓",
            message=哪家公司跌幅多少，提示注意 3312 是否跟進,
            color=COLOR_YELLOW)
      （每個符合條件的同業各一個 Alert）
```

**判斷 3：集團資金撤退聯動**
```
條件：group 中有 code 不在 warned_group 且 pct <= -group_drop_threshold_pct
動作：warned_group.add(code)
      Alert(title="集團股走弱",
            message=哪家公司跌幅多少，提示注意集團資金動向,
            color=COLOR_YELLOW)
```

**判斷 4：指令一 — 開盤看戲（一字鎖漲停）**
```
條件：price >= limit_up
      且 limit_up_opened == False
      且 fired["watch"] == False
動作：fired["watch"] = True
      Alert(title="開盤看戲：強勢鎖漲停",
            message=目前漲停價、提示先續抱看戲,
            color=COLOR_INFO)
```

**判斷 5：指令二 — 短線保本，落袋 2 張**
```
條件（任一）：
    A. price >= target_stage_1
    B. limit_up_opened == True 且 total_volume > alert_volume_threshold
且 fired["stage1"] == False
動作：fired["stage1"] = True
      Alert(title="短線保本，落袋 2 張",
            message=_build_body(snap, "賣出 2 張，收回本金買保險！"),
            color=COLOR_GREEN)
```

**判斷 6：指令三 — 大獲全勝，狙擊 3 張**
```
條件：price >= target_stage_2 且 fired["stage2"] == False
動作：fired["stage2"] = True
      Alert(title="大獲全勝，狙擊 3 張",
            message=_build_body(snap, "已達 85 元估值天花板，全數獲利清倉，風光畢業！"),
            color=COLOR_GREEN)
```

**判斷 7：指令四 — 智慧停利退場（動態防守線）**
```
條件：price <= self.current_stop 且 fired["stop"] == False
動作：fired["stop"] = True
      Alert(title="智慧停利退場",
            message=_build_body(snap,
                f"已跌破防守死線 {self.current_stop} 元，建議將剩餘持股一次清空。"),
            color=COLOR_RED)
```

#### _build_body() 格式

回傳多行字串，依序包含：

1. `【3312 弘憶】現價 X 元（成本 64.86）`
2. `累計量 X 張 ｜ 漲停 X 元`
3. `同業：麗臺 +X% ｜ 聯穎 +X%`（有資料才顯示）
4. `集團：松翰 +X%`（有資料才顯示）
5. `美股昨收：NVDA +X% ｜ SMCI +X%`（有資料才顯示）
6. `目前生效防守線：X 元`
7. `👉 實戰指南：{action}`

---

## 九、main.py 規格

### 執行方式
```bash
python main.py           # 真實模式（需 FUGLE_API_KEY）
python main.py --mock    # 模擬模式（不需任何帳號）
```

### Monitor 類別

**`__init__`**
- `load_config("config.json")` 載入設定。
- 建立 `DiscordNotifier()`。
- 呼叫 `build_market_data(config, use_mock)`。
- 建立 `StrategyEngine(config)`。
- `self.running = True`。

**`run()` 主迴圈**

1. `signal.signal(signal.SIGINT, self._handle_sigint)` 註冊 Ctrl+C。
2. 印啟動訊息（模式 + webhook 是否啟用）。
3. `self.market.start()`，失敗就印錯誤並 return。
4. 主迴圈 `while self.running`：
   - `snap = self.market.snapshot()`
   - `alerts = self.strategy.evaluate(snap)`
   - 對每個 alert 呼叫 `self.notifier.send(a.title, a.message, a.color)`
   - 印心跳行：`[heartbeat] 3312=X 量=X 防守=X`
   - 整個迴圈包在 try-except Exception，捕捉到就印警告並繼續
   - Sleep：用 0.5 秒小步迴圈睡滿 `eval_interval_sec`，
     每步檢查 `self.running`，讓 Ctrl+C 快速響應
5. 迴圈結束後呼叫 `self.market.stop()`，印「已停止」。

**`_handle_sigint`**：設 `self.running = False`，印「收到中止訊號」。

**`if __name__ == "__main__"`**
```python
use_mock = "--mock" in sys.argv
Monitor(use_mock).run()
```

---

## 十、README.md

包含以下內容（繁體中文）：

1. **安裝**：`pip install -r requirements.txt`
2. **環境變數設定**：
   ```bash
   export FUGLE_API_KEY="你的富果 API 金鑰"
   export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
   ```
3. **富果 API 金鑰取得**：免費註冊 fugle.tw 會員，在開發者頁面申請，**不需要開券商帳號**。
4. **Discord Webhook 取得**：伺服器 → 頻道設定 → 整合 → Webhook → 複製網址。
5. **執行指令**：mock 和真實兩種。
6. **訂閱數說明**：免費方案上限 5 訂閱，此程式用 4 個（4 檔 × aggregates channel），
   剛好在限制內。請勿自行增加訂閱其他 channel，否則會超量報錯。
7. **部署提醒**：程式要在盤中持續跑，建議放常開的主機或雲端 VM。
8. **上線前三項必確認**：
   - 4 檔股票代號（3312、2465、3550、5471）是否都能正常訂閱（富果有支援）
   - `stop_loss_tightened`（64.5）低於成本 `cost_price`（64.86）的邏輯矛盾，
     美股利空觸發後停損會是小賠出場，請自行決定是否調高
   - 盤前盤後 WebSocket 沒有報價推播屬正常，監控程式只在開盤時間有效
9. **免責聲明**：本程式依使用者自訂規則發送提醒，不預測股價，不構成投資建議。

---

## 十一、品質要求

1. **所有程式碼包含繁體中文注解**，說明每個重要判斷的用途。
2. **不省略任何程式碼**，每個檔案都必須完整、可直接執行。
3. `MockMarketData` 和 `RealMarketData` 的 `snapshot()` 回傳格式**完全相同**，
   `strategy.py` 和 `main.py` 對兩者透明。
4. 所有網路呼叫（Discord POST、yfinance、Fugle WebSocket）都要有 try-except，
   失敗只印警告，不崩潰。
5. Fugle WebSocket message 回呼一律用 `threading.Lock` 保護共享狀態。
6. 去重機制：同一警報不重複發送（`fired` / `warned_*` 旗標）。
7. 不使用任何 UI 套件。

---

## 十二、完成驗證

全部檔案建立後，請執行以下指令確認可正常啟動：

```bash
pip install requests        # mock 模式只需這個
python main.py --mock
```

**預期輸出：**
- 印出「3312 監控啟動（模式：模擬）」
- 每 5 秒印一行 heartbeat，顯示模擬股價與防守線
- 沒設 DISCORD_WEBHOOK_URL 時，警報直接印在終端機
- Ctrl+C 後印「已停止」並正常退出（exit code 0）