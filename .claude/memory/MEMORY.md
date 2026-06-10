# Smart Monitor Memory Index

## API 與技術整合

- Fugle API marketdata v1.0 串接方法、認證格式、端點範例 → 見 [../FUGLE_API.md](../FUGLE_API.md)
- [fugle_candles_lag.md](fugle_candles_lag.md) — 歷史日K落後一個交易日，今日收盤要用即時報價補上 K 線尾端
- [stock_picker_spec.md](stock_picker_spec.md) — 選股推薦（Phase B）完整設計規格：3題問答、策略對應、資金篩選、快取、每日10次上限
- [finmind_limitation.md](finmind_limitation.md) — FinMind 免費方案無法存取三大法人資料，籌碼面篩選目前失效（aggressive_short、momentum_mid 策略選股會失敗）

## 開發守則 / 易踩坑

- [discord_webhook_precedence.md](discord_webhook_precedence.md) — DiscordNotifier 的 webhook_url 必須「傳入參數優先、環境變數後備」，否則 error 頻道通知會誤發到一般頻道
