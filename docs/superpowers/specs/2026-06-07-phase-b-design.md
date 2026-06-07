# Smart Monitor Phase B — 選股推薦服務設計文件

**日期：** 2026-06-07  
**範疇：** 每日自動選股推薦服務（策略插件架構）

---

## 一、目標

建立每日自動選股推薦服務，透過籌碼面 + 技術面組合篩選全市場股票，提供：
1. 每日 08:00 自動掃描推播推薦清單給訂閱使用者
2. 使用者可查看推薦、決定是否訂閱每日推播
3. Claude API 生成白話說明（推薦理由 + 風險提示）
4. 可擴展的策略插件架構，支持未來新增策略

---

## 二、架構設計

### 整體流程

```
定時排程 08:00
    ↓
StockPickerEngine.scan()
    ├── FundamentalStrategy.scan() → [股票列表]
    ├── TechnicalStrategy.scan() → [股票列表]
    └── 取交集 → 最終推薦清單
    ↓
Claude API 生成說明文案（每支股票）
    ↓
推播給所有訂閱使用者（LINE + Discord）
    ↓
使用者可「輸入 4」查看推薦 → ScriptedService 互動
```

### 分層架構

**第 1 層：策略（Strategy）**
- 定義策略基類 `Strategy`
- 實作 `FundamentalStrategy`（籌碼面）
- 實作 `TechnicalStrategy`（技術面）
- 未來擴展：基本面、消息面等

**第 2 層：掃描引擎（Scanner）**
- `StockPickerEngine` — 組合多個策略
- 執行 `scan()`，返回符合條件的股票清單
- 按邏輯組合結果（交集 / 聯集）

**第 3 層：服務（Service）**
- `StockPickerService`（ScriptedService 子類）— 用戶互動
- 支持訂閱/取消訂閱
- 顯示推薦清單

**第 4 層：外部 API**
- `FugleClient`（已有）— 日K 資料
- `FinMindClient`（新建）— 籌碼面資料
- Claude API — 生成說明文案

---

## 三、資料結構

### 使用者訂閱狀態（user_store.py 擴充）

在 `state.json` 新增欄位：
```json
{
  "services": {
    "stock_picker_subscribed": true,
    "stock_picker_last_view": "2026-06-07"
  }
}
```

### 推薦結果快取（stock_picker.json）

每日 08:00 掃描結果快取在 `data/` 目錄（非使用者專屬）：
```json
{
  "date": "2026-06-07",
  "timestamp": 1717752000,
  "stocks": [
    {
      "stock_id": "2330",
      "stock_name": "台積電",
      "current_price": 920.0,
      "reasons": {
        "fundamental": "三大法人連 3 日買超，融資餘額下降",
        "technical": "MA20 上升，距離高點回撤 3.5%"
      },
      "risks": "若跌破 MA20 應設停損",
      "claude_summary": "[Claude 生成的白話說明]"
    }
  ]
}
```

---

## 四、策略設計

### Strategy 基類

```python
from typing import List, Dict

class Stock:
    stock_id: str
    stock_name: str
    # 其他欄位...

class Strategy:
    """策略基類"""
    name: str
    
    def scan(self) -> List[Stock]:
        """掃描符合條件的股票，回傳代號列表"""
        raise NotImplementedError()
```

### FundamentalStrategy（籌碼面）

**資料來源：** FinMind API

**篩選條件（ALL）：**
1. 三大法人連續 N 天買超（可配置，預設 3 天）
2. 融資餘額增加比例 < 5%（避免融資爆增）
3. 股票交易量 > 平均值（排除冷門股）

**實作概要：**
```python
class FundamentalStrategy(Strategy):
    def __init__(self, finmind_client, days=3):
        self.client = finmind_client
        self.days = days
    
    def scan(self) -> List[Stock]:
        # 取 FinMind 數據
        # 篩選三大法人連續買超
        # 篩選融資正常增長
        # 篩選交易量足夠
        # 回傳符合條件的股票列表
        pass
```

### TechnicalStrategy（技術面）

**資料來源：** Fugle API（日K 資料）

**篩選條件（ALL）：**
1. 收盤價 > MA20（趨勢向上）
2. 距離 20 日高點回撤 < 8%（未過度下跌）
3. 過去 5 日有上漲（動能未衰）

**實作概要：**
```python
class TechnicalStrategy(Strategy):
    def __init__(self, fugle_client):
        self.client = fugle_client
    
    def scan(self) -> List[Stock]:
        # 遍歷所有股票
        # 計算 MA20、高點回撤、動能
        # 篩選符合條件的股票
        # 回傳列表
        pass
```

---

## 五、掃描引擎設計

### StockPickerEngine

```python
class StockPickerEngine:
    def __init__(self, strategies: List[Strategy]):
        self.strategies = strategies
    
    def scan(self) -> List[Stock]:
        """
        執行所有策略，取交集。
        回傳同時符合所有策略條件的股票。
        """
        results = []
        for strategy in self.strategies:
            results.append(set(strategy.scan()))
        
        # 交集
        intersection = results[0]
        for i in range(1, len(results)):
            intersection &= results[i]
        
        return list(intersection)
```

### 每日排程

使用 APScheduler 或 cron：
```python
# 08:00 UTC+8 執行
scheduler.add_job(
    func=daily_stock_picker_task,
    trigger="cron",
    hour=0,  # UTC 時區
    minute=0,
    id="stock_picker_daily"
)

async def daily_stock_picker_task():
    engine = StockPickerEngine([
        FundamentalStrategy(finmind_client),
        TechnicalStrategy(fugle_client),
    ])
    
    stocks = engine.scan()
    
    # 生成 Claude 說明
    for stock in stocks:
        stock.claude_summary = claude_client.generate_summary(stock)
    
    # 快取結果
    cache_results(stocks)
    
    # 推播給訂閱使用者
    broadcast_to_subscribers(stocks)
```

---

## 六、服務設計（用戶互動）

### StockPickerService（ScriptedService 子類）

**目的：** 用戶查看推薦清單、管理訂閱

**互動流程：**
```
用戶輸入「4」
    ↓
顯示推薦清單（如果今日已掃描）
    ├─ 📈 推薦 N 支股票（日期）
    ├─ 1️⃣ 台積電（2330）— 理由：xxx
    ├─ 2️⃣ 聯發科（2454）— 理由：xxx
    ├─ ...
    ↓
用戶選項：
    ├─ 「詳細 [數字]」 → 展開該股票的詳細說明 + 風險提示
    ├─ 「訂閱」 → 每日 08:00 自動推播
    ├─ 「取消訂閱」 → 停止推播
    └─ 「取消」 → 回到主選單
```

**實作概要：**
```python
class StockPickerService(ScriptedService):
    name = "stock_picker"
    
    def start(self, uid, store, line):
        # 讀取今日推薦快取
        # 顯示清單 + 說明
        # 進入狀態 "stock_picker_view"
    
    def on_complete(self, uid, draft, store, line):
        # 處理訂閱/詳細查看
        if draft["action"] == "subscribe":
            store.set_subscription(uid, "stock_picker", True)
```

---

## 七、FinMind API 整合

### FinMindClient

新建 `bot/stock_picker/finmind_client.py`

```python
class FinMindClient:
    def get_three_major_buyers(self, stock_id: str, days: int = 3) -> Dict:
        """
        取得三大法人買賣超資料
        回傳：{"buy_excess_days": 3, "total_buy": 10000000, ...}
        """
    
    def get_margin_status(self, stock_id: str) -> Dict:
        """
        取得融資融券狀態
        回傳：{"margin_balance": 5000000, "short_balance": 1000000, ...}
        """
    
    def get_all_stocks_basic(self) -> List[Dict]:
        """載入全市場股票基本資訊"""
```

**環境變數：**
```
FINMIND_API_KEY=<金鑰>
```

---

## 八、Claude API 說明生成

### 說明生成邏輯

使用 Claude API 根據籌碼面 + 技術面資料生成白話說明：

```python
def generate_stock_summary(stock_id: str, reasons: Dict) -> str:
    """
    輸入：
      stock_id: "2330"
      reasons: {
        "fundamental": "三大法人連 3 日買超",
        "technical": "MA20 上升，回撤 3.5%"
      }
    
    輸出：Claude 生成的白話說明
    """
    prompt = f"""
    你是台股分析師。用白話解釋為什麼這支股票值得注意：
    
    股票：{stock_id}
    籌碼面理由：{reasons['fundamental']}
    技術面理由：{reasons['technical']}
    
    請用 2-3 句話解釋，對象是不懂技術面的投資人。
    """
    
    response = claude_client.messages.create(
        model="claude-opus-4-8",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.content[0].text
```

---

## 九、推播設計

### 每日推播訊息格式

```
📈 Smart Monitor 每日選股推薦（2026-06-07）

今日掃描 1,520 支股票，發現 3 支值得關注：

1️⃣ 台積電（2330）
   現價：920 元
   📌 理由：三大法人連 3 日買超、MA20 上升
   ⚠️ 風險：若跌破 MA20 應設停損

2️⃣ 聯發科（2454）
   現價：1,180 元
   📌 理由：...

3️⃣ ...

輸入『4』查看詳細說明或訂閱每日推播
```

### 推播時機

- **自動推播時間：** 每日 UTC+8 08:00（交易前）
- **推播對象：** 所有訂閱使用者
- **推播管道：** LINE push + Discord webhook

---

## 十、權限系統

### 服務可用性

| 服務 | free | basic | pro |
|------|------|-------|-----|
| 股票監控 | ✅ 1 支 | ✅ 3 支 | ✅ 3 支 |
| 盤前/盤後分析 | ❌ | ✅ | ✅ |
| **選股推薦** | **❌** | **✅** | **✅** |

自由方案使用者輸入「4」時回覆：
```
⚠️ 選股推薦為 basic 以上方案的功能。
請聯絡管理員了解升級方式。
```

---

## 十一、狀態圖

```
使用者輸入「4」
    ↓
check_permission(uid, "stock_picker")
    ├─ 無權限 → 顯示升級提示，回到主選單
    └─ 有權限 ↓
      讀取今日推薦快取
        ├─ 快取存在 → 顯示清單
        └─ 不存在 → 顯示「今日掃描未開始」
        ↓
      用戶選擇：
        ├─ 「詳細 1」 → 展開說明 + 風險提示
        ├─ 「訂閱」 → store.set_subscription(uid, "stock_picker", True)
        ├─ 「取消訂閱」 → store.set_subscription(uid, "stock_picker", False)
        └─ 「取消」 → 回到主選單
```

---

## 十二、不在此次範疇

- 即時股價提醒（已在 Phase A 的監控服務）
- 基本面分析（EPS、本益比等）
- 消息面追蹤
- 選股策略的機器學習優化

---

## 十三、實作檢查清單

- [ ] FinMindClient 整合
- [ ] FundamentalStrategy 實作
- [ ] TechnicalStrategy 實作
- [ ] StockPickerEngine 整合
- [ ] 每日排程設定
- [ ] StockPickerService（ScriptedService）
- [ ] 推薦結果快取邏輯
- [ ] Claude API 說明生成
- [ ] 權限檢查（basic/pro 才能用）
- [ ] 訂閱狀態管理
- [ ] 推播給訂閱使用者
- [ ] 單元測試（各策略、引擎、服務）
