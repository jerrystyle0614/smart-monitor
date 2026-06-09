---
name: fugle_candles_lag
description: Fugle 歷史日K端點落後一個交易日，今日收盤要從即時報價補上
metadata: 
  node_type: memory
  type: reference
  originSessionId: 86325131-93ca-477f-8c28-c50e857d1617
---

# Fugle 歷史日K落後一天，今日收盤需用即時報價補上

Fugle 官方 `historical/candles` 端點（`fugle_marketdata` SDK 的 `client.stock.historical.candles`）
在盤後查詢時，**最新一筆通常只到前一個交易日**，當日資料尚未入庫。

實測（2026-06-08 盤後查 3312）：
- `historical/candles` 最後一筆 = 2026-06-05 收盤 67.5（昨日）
- `intraday/quote` = `closePrice: 60.8`、`previousClose: 67.5`（今日正確收盤）

## 後果
盤後分析若直接取歷史日K最後一筆當「今日收盤」，會顯示昨日價，
且 MA20／高點回撤等技術指標也全部落後一天。

## 解法
`fetch_candles` 取得歷史日K後，再呼叫 `intraday/quote`，
若 `quote.date == today` 且歷史尾端非今日，就把今日 K 線（用即時報價組成）
`pd.concat` 接到 DataFrame 尾端。盤前時段今日尚無成交，`quote.date != today`，自動不補。

兩條路徑都要套用（兩個不同的 fetch_candles）：
- [bot/data/fugle_client.py](../../bot/data/fugle_client.py) — `FugleClient.fetch_candles` + `_append_today_candle`（AnalysisEngine 主路徑）
- [daily_data.py](../../daily_data.py) — `fetch_candles` + `_append_today_candle`（analysis_runner fallback 路徑）

相關：[[fugle_api_integration]]
