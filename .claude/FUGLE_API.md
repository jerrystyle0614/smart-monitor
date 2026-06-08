# Fugle API 串接指南

## 正確的 API 端點

```
https://api.fugle.tw/marketdata/v1.0
```

**不正確的端點（已淘汰）:**
- ❌ `https://api.fugle.tw/realtime/v0.3` — 會返回 400/401 錯誤
- ❌ `https://api.fugle.tw/v0/...` — 已停用

## 認證方式

### Header 格式

```python
headers = {
    "X-API-KEY": FUGLE_API_KEY  # 原始 Base64 編碼的 Key，不需解碼
}
```

**錯誤的認證:**
- ❌ `X-FUGLE-APIKEY` — 會返回 401
- ❌ `apiToken` query parameter — 舊格式，已移除

## API Key 處理

```python
# ✅ 正確：直接使用環境變數的原始值
raw_key = os.environ.get("FUGLE_API_KEY")  # 保持 Base64 格式
headers = {"X-API-KEY": raw_key}

# ❌ 錯誤：解碼後使用
decoded = base64.b64decode(raw_key).decode('utf-8')
# 這會導致 401 認證失敗
```

## API 端點範例

### 1. 即時報價

```
GET https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}
```

**回應格式（注意是扁平結構）:**

```json
{
  "date": "2026-06-08",
  "symbol": "2330",
  "name": "台積電",
  "closePrice": 2295.00,
  "change": -70,
  "changePercent": -2.96,
  "highPrice": 2320,
  "lowPrice": 2230,
  "openPrice": 2230,
  "avgPrice": 2284.98,
  "lastPrice": 2295,
  "lastSize": 4454
}
```

**Python 範例:**

```python
import requests
import os

headers = {"X-API-KEY": os.environ.get("FUGLE_API_KEY")}
url = "https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/2330"

resp = requests.get(url, headers=headers, timeout=5)
data = resp.json()

# 提取數據（扁平結構）
stock_name = data.get("name")
close_price = data.get("closePrice")
change_pct = data.get("changePercent")
```

### 2. K 線資料

```
GET https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles/{symbol}
```

### 3. 股票資訊

```
GET https://api.fugle.tw/marketdata/v1.0/stock/intraday/ticker/{symbol}
```

## 常見問題排查

| 錯誤 | 原因 | 解決方案 |
|------|------|--------|
| HTTP 401 | 認證失敗 | 檢查 API Key 格式和 X-API-KEY header |
| HTTP 404 | 端點不存在 | 確認使用 `/marketdata/v1.0` 而非舊端點 |
| 無法取得報價 | API Key 無權限 | 聯絡 Fugle 客服確認帳號權限 |

## 與其他框架整合

### Node.js / TypeScript

```typescript
const headers = {
  'X-API-KEY': process.env.FUGLE_API_KEY,
  'Content-Type': 'application/json',
}

const url = `https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/${symbol}`
const response = await axios.get(url, { headers })
```

### Python requests

```python
import requests
import os

headers = {"X-API-KEY": os.environ.get("FUGLE_API_KEY")}
response = requests.get(url, headers=headers, timeout=5)
data = response.json()
```

## 實作檢查清單

- ✅ 使用 `marketdata/v1.0` 端點
- ✅ Header 用 `X-API-KEY`（大寫）
- ✅ API Key 保持 Base64 格式，不解碼
- ✅ 回應是扁平結構（直接存取 `closePrice`，不是 `data.quote.trade.price`）
- ✅ 股票代號轉大寫（通常 `2330` 可用）

## 實作文件

- Python 實作：`bot/data/fugle_client.py`
- Fugle 官方文檔：https://developer.fugle.tw/
