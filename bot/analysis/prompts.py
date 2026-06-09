"""
prompts.py — Claude 分析 Prompt Templates
"""

# 技術面分析 Prompt（通用，無市場背景）
TECHNICAL_ANALYSIS_PROMPT = """
分析股票 {stock_name}({stock_id}) 的技術面。

最近 20 日 K 線資料：
{candle_data}

請提供以下分析（用繁體中文，避免複雜術語）：

1. **目前走勢**：
   - 簡述趨勢方向（上升/下降/盤整）
   - 支撐價位、壓力價位

2. **技術形態**：
   - 觀察到的形態（如：雙底、三角形、旗形等）
   - 形態的意義

3. **動量指標**：
   - 成交量變化
   - 最近是否有異常訊號

回應格式：JSON
{{
  "trend": "上升/下降/盤整",
  "support": 123.45,
  "resistance": 125.50,
  "pattern": "形態名稱",
  "volume_signal": "訊號評估",
  "summary": "白話總結"
}}
"""

# 盤前技術面分析 Prompt（含市場背景，整合分析）
TECHNICAL_ANALYSIS_PRE_MARKET_PROMPT = """
分析股票 {stock_name}({stock_id}) 的技術面，並結合今日盤前市場背景做出綜合判斷。

{market_context}

最近 20 日 K 線資料：
{candle_data}

請提供以下分析（用繁體中文，避免複雜術語）：

1. **目前走勢**：
   - 簡述趨勢方向（上升/下降/盤整）
   - 支撐價位、壓力價位

2. **技術形態**：
   - 觀察到的形態（如：雙底、三角形、旗形等）
   - 形態的意義

3. **動量指標**：
   - 成交量變化
   - 最近是否有異常訊號

4. **市場連動影響**（根據上方市場背景）：
   - 美股/台指期夜盤昨夜表現對今日開盤的影響方向
   - 此股票是否對外部指數敏感（如科技股對 SOX/Nasdaq、金融股對匯率）
   - 今日開盤偏多或偏空的預判

回應格式：JSON
{{
  "trend": "上升/下降/盤整",
  "support": 123.45,
  "resistance": 125.50,
  "pattern": "形態名稱",
  "volume_signal": "訊號評估",
  "market_impact": "市場背景影響說明",
  "open_bias": "偏多/偏空/中性",
  "summary": "白話總結（含市場背景影響）"
}}
"""

# 進出場建議 Prompt
ENTRY_EXIT_PROMPT = """
根據技術面分析結果，給予進出場建議。

股票：{stock_name}({stock_id})
目前價格：{current_price}
技術分析：{technical_analysis}
分析時間：{analysis_time}（盤前/盤後）

請提供：
1. **進場建議**：
   - 建議進場價位
   - 買進理由（從技術面角度）
   - 風險等級（低/中/高）

2. **出場建議**：
   - 目標價位（短期/中期）
   - 停損價位
   - 獲利/虧損潛力

3. **操作提示**：
   - 今日適合操作嗎？
   - 主要關注點

回應格式：JSON
{{
  "entry_price": 124.0,
  "entry_reason": "原因",
  "exit_targets": {{"short_term": 125.0, "medium_term": 127.0}},
  "stop_loss": 122.0,
  "risk_level": "中",
  "suitable_today": true,
  "watch_points": "注意事項"
}}
"""

# 風險提示 Prompt
RISK_ALERT_PROMPT = """
根據技術面和進出場分析，提供風險提示。

股票：{stock_name}({stock_id})
技術分析：{technical_analysis}
進出場建議：{entry_exit_analysis}

請警示潛在風險（用白話文，避免造成恐慌）：
1. 技術面風險（形態失敗、支撐破位等）
2. 操作風險（進場時機、資金控管）
3. 市場風險（交易量不足、流動性問題）

回應格式：JSON
{{
  "technical_risks": ["風險 1", "風險 2"],
  "operation_risks": ["風險 1"],
  "market_risks": ["風險 1"],
  "overall_caution_level": "低/中/高"
}}
"""
