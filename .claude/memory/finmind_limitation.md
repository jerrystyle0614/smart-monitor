---
name: finmind-limitation
description: FinMind 免費方案無法存取三大法人資料，籌碼面篩選目前失效
metadata: 
  node_type: memory
  type: project
  originSessionId: ecfb8942-3a00-4835-a2a2-336f58ab8b09
---

FinMind 免費方案不支援 `TaiwanStockInstitutionalInvestorsBuySell` dataset，呼叫會回傳 403 Forbidden。

**Why:** 三大法人買賣超資料在 FinMind 付費牆後面，目前使用免費帳號。

**How to apply:**
- `get_three_major_buyers()` 永遠回傳 `None`
- prescan 的投信過濾形同虛設（trust_net 預設 0，不觸發過濾）
- `_scan_stocks` 中 `require_institutional_buy: True` 的策略（aggressive_short、momentum_mid）會把所有候選股擋掉，導致選股失敗
- 目前只有 defensive_band、high_yield_stable、dca_stable 三個策略能正常運作
- 待升級 FinMind 付費方案後才能修復
