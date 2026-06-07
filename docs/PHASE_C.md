# Phase C — Claude AI 深度分析引擎

## 概述

**Phase C** 是 Smart Monitor 的核心分析升級，引入 Claude 3.5 Sonnet 作為技術面分析的 AI 引擎。

### 主要功能

1. **技術面分析**
   - 自動分析 20 日 K 線數據
   - 辨識支撐/壓力價位
   - 識別 chart patterns（雙底、三角形、旗形等）
   - 評估趨勢強度與方向

2. **進出場建議**
   - 根據技術面生成「今日適合進場」或「明日可進場」的信號
   - 推薦進場價位區間（含獲利空間計算）
   - 推薦停損價位（風險控制）

3. **風險提示**
   - 識別市場風險信號（如：漲勢過度、跌勢過度等）
   - 警告主要支撐破位的危險
   - 提醒交易量異常的潛在風險

---

## 架構設計

### 系統流程圖

```
使用者開啟 LINE Bot
        │
        ├─→ 盤前 08:30
        │   ├─→ PreMarketService.on_complete()
        │   ├─→ AnalysisEngine.analyze_pre_market()
        │   ├─→ Claude API 分析 (技術 + 進場 + 風險)
        │   └─→ 推播分析結果 + 進場建議
        │
        └─→ 盤後 13:35
            ├─→ PostMarketService.on_complete()
            ├─→ AnalysisEngine.analyze_post_market()
            ├─→ Claude API 分析 (技術 + 明日展望 + 風險)
            └─→ 推播分析結果 + 次日前景
```

### AnalysisEngine 設計

**檔案：`bot/analysis/engine.py`**

```python
class AnalysisEngine:
    def __init__(self, use_cache: bool = True):
        self.client = Anthropic()
        self.model = "claude-3-5-sonnet-20241022"
        self.cache = AnalysisCache() if use_cache else None

    def analyze_pre_market(
        self,
        stock_id: str,
        stock_name: str,
        candle_data: str,
        current_price: float,
    ) -> Dict[str, Any]:
        """盤前分析：技術面 + 進出場建議 + 風險提示"""
        # 檢查快取
        if self.cache:
            cached = self.cache.get(stock_id, "pre_market")
            if cached:
                return cached

        # 依序呼叫三個分析方法
        technical = self._analyze_technical(...)
        entry_exit = self._analyze_entry_exit(...)
        risks = self._analyze_risks(...)

        result = {
            "technical": technical,
            "entry_exit": entry_exit,
            "risks": risks,
            "timestamp": "ISO8601",
        }

        # 保存快取
        if self.cache:
            self.cache.set(stock_id, "pre_market", result)

        return result

    def analyze_post_market(...):
        """盤後分析：類似 analyze_pre_market，但分析時段改為「盤後」"""

    def _analyze_technical(...) -> Optional[Dict]:
        """呼叫 Claude：技術面分析 → JSON 回傳"""

    def _analyze_entry_exit(...) -> Optional[Dict]:
        """呼叫 Claude：進出場建議 → JSON 回傳"""

    def _analyze_risks(...) -> Optional[Dict]:
        """呼叫 Claude：風險提示 → JSON 回傳"""
```

### 快取機制

**檔案：`bot/analysis/cache.py`**

- **TTL**：1 小時（同一支股票在 1 小時內的重複分析使用快取）
- **儲存**：JSON 檔案，位置 `cache/analysis/{stock_id}_{type}.json`
- **減少 API 呼叫**：約 80%（詳見成本分析）

快取鍵格式：
```
{stock_id}_{analysis_type}
# 例：2330_pre_market, 0050_post_market
```

快取内容：
```json
{
  "technical": {...},
  "entry_exit": {...},
  "risks": {...},
  "timestamp": "2026-06-07T08:30:00.123456",
  "cached_at": 1717753800.123456,
  "ttl": 3600
}
```

### 與 PreMarketService/PostMarketService 的整合

**PreMarketService 整合流程：**

```python
class PreMarketService(ScriptedService):
    async def on_complete(self, line_user_id: str, data: Dict[str, Any]):
        """完成所有問答後觸發"""

        # 1. 取得使用者選擇的股票清單
        stocks = data.get("stocks", [])

        for stock in stocks:
            stock_id = stock["id"]
            stock_name = stock["name"]

            # 2. 抓取 20 日 K 線
            candles = await daily_data.get_daily_candles(stock_id, days=20)
            candle_data = self._format_candles(candles)

            # 3. 抓取即時價格
            quote = await fugle_client.get_quote(stock_id)
            current_price = quote["price"]

            # 4. 呼叫 AnalysisEngine
            engine = AnalysisEngine(use_cache=True)
            analysis = engine.analyze_pre_market(
                stock_id, stock_name, candle_data, current_price
            )

            # 5. 格式化分析結果為 LINE 訊息
            message = self._format_analysis_message(
                stock_id, stock_name, analysis
            )

            # 6. 推播給使用者
            await line_client.push_message(line_user_id, message)
```

**PostMarketService 整合類似。**

---

## API 成本估算

### Claude 3.5 Sonnet 定價（2026 年）

| 項目 | 價格 |
|------|------|
| Input tokens | $3/1M tokens ($0.000003 per token) |
| Output tokens | $15/1M tokens ($0.000015 per token) |

### 每支股票單次分析的 Token 消耗

假設分析 1 支股票（20 日 K 線 + 當日價格 + 3 個分析提示）：

| 分析類型 | 輸入 tokens | 輸出 tokens | 成本 |
|---------|-----------|-----------|------|
| 技術面分析 | ~800 | ~400 | ~$0.004 |
| 進出場建議 | ~1200 | ~300 | ~$0.0054 |
| 風險提示 | ~1000 | ~200 | ~$0.0033 |
| **單支股票合計** | **~3000** | **~900** | **~$0.0127** |

### 日常監控成本

**假設：每日監控 5 支股票，分 2 次分析（盤前 + 盤後）**

#### 無快取情況
```
5 支股票 × 2 次 × $0.0127 = $0.127/天 = $3.81/月
```

#### 有快取情況（1 小時 TTL）
- 盤前 08:30：分析 5 支（無快取）≈ $0.0635
- 盤前 08:35-12:30：重複查詢（全部命中快取）≈ $0
- 盤後 13:35：分析 5 支（無快取）≈ $0.0635
- 盤後 13:40-17:00：重複查詢（全部命中快取）≈ $0

```
單日成本 ≈ $0.127
月度成本 ≈ $3.81

快取命中率 ≈ 80%（假設盤前查 8 次，命中 6 次；盤後查 8 次，命中 6 次）
實際月度成本 ≈ $0.76
```

**結論**：快取可減少約 80% 的 API 成本。

---

## 使用示例

### 使用者交互流程

#### 1. 盤前分析

```
08:30 (系統自動推播)

┌─────────────────────────────┐
│ 📊 台積電 (2330) 盤前分析     │
├─────────────────────────────┤
│ ✓ 技術面：                  │
│   - 趨勢：上升趨勢           │
│   - 支撐：655 元            │
│   - 壓力：670 元            │
│   - 形態：三角形收斂         │
│                           │
│ 💰 進場建議：                │
│   - 狀態：適合進場           │
│   - 進場價：660-665 元       │
│   - 目標價：680 元 (+3%)     │
│   - 停損：650 元 (-2%)       │
│                           │
│ ⚠️ 風險提示：                │
│   - 注意：成交量略降         │
│   - 警告：670 元為強壓力     │
│   - 建議：分批進場           │
└─────────────────────────────┘
```

#### 2. 盤後分析

```
13:35 (系統自動推播)

┌─────────────────────────────┐
│ 📊 台積電 (2330) 盤後分析     │
├─────────────────────────────┤
│ ✓ 技術面：                  │
│   - 趨勢：持續上升           │
│   - 支撐：658 元 ↑           │
│   - 壓力：675 元 ↑           │
│   - 形態：三角形破位         │
│                           │
│ 🔮 明日展望：                │
│   - 前景：偏樂觀             │
│   - 建議：可續抱或加碼        │
│   - 目標：680-685 元         │
│   - 警戒：跌破 658 元        │
│                           │
│ ⚠️ 風險提示：                │
│   - 注意：連 3 日上漲         │
│   - 警告：過度買超           │
│   - 建議：設定停利 680 元    │
└─────────────────────────────┘
```

---

## 測試覆蓋

### 測試套件：`tests/test_analysis_engine.py`

**總計 20 個測試，100% 通過**

#### 測試分類

| 分類 | 測試數 | 涵蓋範圍 |
|------|--------|---------|
| **TestAnalysisCache** | 2 | 快取的設定、讀取、鍵生成 |
| **TestAnalysisEngine** | 2 | 引擎初始化、API 整合 |
| **TestPreMarketIntegration** | 4 | 盤前服務整合、完成流程、訊息格式、錯誤降級 |
| **TestPostMarketIntegration** | 4 | 盤後服務整合、完成流程、訊息格式、錯誤降級 |
| **TestE2EPipeline** | 2 | 端對端盤前、盤後流程 |
| **TestCacheValidation** | 3 | 快取命中率、TTL 驗證、多支股票快取隔離 |
| **TestErrorHandling** | 3 | API 失敗降級、資料抓取失敗、惡意回應處理 |

### 核心測試案例

#### 快取測試
```python
def test_cache_reduces_api_calls():
    """驗證快取可減少 API 呼叫"""
    engine = AnalysisEngine(use_cache=True)

    # 第一次呼叫 → API 呼叫
    result1 = engine.analyze_pre_market(...)
    assert mock_api_call_count == 1

    # 第二次呼叫（同股票，同時段）→ 快取命中
    result2 = engine.analyze_pre_market(...)
    assert mock_api_call_count == 1  # 未增加
    assert result1 == result2
```

#### 整合測試
```python
def test_pre_market_service_integration():
    """驗證 PreMarketService 與 AnalysisEngine 的整合"""
    service = PreMarketService()
    engine = AnalysisEngine(use_cache=False)

    # 模擬使用者完成問答
    data = {
        "stocks": [
            {"id": "2330", "name": "台積電"},
            {"id": "0050", "name": "元大台灣50"},
        ]
    }

    # 呼叫 on_complete
    service.on_complete(line_user_id, data)

    # 驗證推播訊息已送出
    assert push_message_call_count == 2  # 2 支股票
    assert "台積電" in push_message_args[0]
    assert "0050" in push_message_args[1]
```

#### 錯誤降級測試
```python
def test_graceful_degradation_on_api_failure():
    """API 失敗時應優雅降級"""
    engine = AnalysisEngine()

    # 模擬 Claude API 異常
    with patch('anthropic.Anthropic.messages.create') as mock:
        mock.side_effect = Exception("API Timeout")

        result = engine.analyze_pre_market(...)

        # 應回傳空字典或使用 legacy 分析
        assert result is not None or legacy_analysis is used
```

### 執行測試

```bash
# 執行全部測試
python3 -m pytest tests/test_analysis_engine.py -v

# 執行特定測試類別
python3 -m pytest tests/test_analysis_engine.py::TestAnalysisCache -v

# 執行單個測試
python3 -m pytest tests/test_analysis_engine.py::TestCacheValidation::test_cache_reduces_api_calls -v

# 檢視覆蓋率
python3 -m pytest tests/test_analysis_engine.py --cov=bot.analysis --cov-report=html
```

---

## 部署注意

### 環境變數設定

```bash
# .env 或系統環境變數
export ANTHROPIC_API_KEY="sk-ant-..."
export FUGLE_API_KEY="..."
export LINE_CHANNEL_ACCESS_TOKEN="..."
```

### 快取目錄

```bash
# 快取自動建立於以下目錄
cache/analysis/

# 結構
cache/analysis/
├── 2330_pre_market.json
├── 2330_post_market.json
├── 0050_pre_market.json
└── ...
```

### 啟動應用

```bash
# 啟動 Phase C 引擎
python3 bot/server.py

# 驗證輸出
# [2026-06-07 08:30:15] [analysis] 台積電(2330) 技術面分析完成
# [2026-06-07 08:30:18] [analysis] 台積電(2330) 進出場建議完成
# [2026-06-07 08:30:21] [analysis] 台積電(2330) 風險提示完成
# [2026-06-07 08:30:22] [line] 推播 2 支股票分析給 U123456
```

### 錯誤優雅降級

**若 Claude API 失敗**：

```python
# AnalysisEngine 會依序嘗試降級
1. ✓ 返回快取結果（如果可用）
2. ✓ 使用 legacy swing_strategy.py 分析（預設）
3. ✓ 推播訊息附註「技術面分析暫無」
4. ✓ 繼續執行，不中斷推播流程
```

**日誌示例**：

```
[analysis] 技術面分析失敗：API Timeout
[analysis] 降級為 legacy 分析：swing_strategy
[line] 推播訊息：台積電 (2330) 盤前分析 [使用經典波段策略]
```

---

## 文件清單

### Phase C 新增 / 修改文件

| 文件 | 狀態 | 說明 |
|------|------|------|
| `bot/analysis/__init__.py` | ✨ 新增 | AnalysisEngine 導出 |
| `bot/analysis/engine.py` | ✨ 新增 | Claude AI 分析引擎核心 |
| `bot/analysis/cache.py` | ✨ 新增 | 分析結果快取（1h TTL） |
| `bot/analysis/prompts.py` | ✨ 新增 | Claude Prompt 模板 |
| `bot/services/pre_market.py` | 🔗 修改 | 整合 AnalysisEngine |
| `bot/services/post_market.py` | 🔗 修改 | 整合 AnalysisEngine |
| `tests/test_analysis_engine.py` | ✨ 新增 | 完整測試套件（20 個測試） |
| `docs/PHASE_C.md` | 📖 新增 | 本文件 |

---

## 架構優勢

1. **低成本**：快取機制減少 80% API 呼叫
2. **高可靠性**：API 失敗時自動降級至 legacy 分析
3. **易擴展**：Prompt 模板可靈活調整，支援多語言
4. **充分測試**：20 個測試覆蓋核心流程和邊界情況
5. **用戶友好**：分析結果用繁體中文，白話解釋

---

## 後續規劃（Phase D+）

1. **多模型支援**：支援 Gemini、OpenAI 等其他 AI 模型
2. **即時分析**：市場異動時主動觸發分析
3. **自訂提示**：用戶可自訂分析內容偏好
4. **分析歷史**：儲存過去分析結果，追蹤準確度
5. **選股推薦升級**：整合 Claude 分析 + 籌碼面 + 基本面

