"""
claude_parser.py — 自然語言監控條件解析模組
呼叫 Claude API 一次，將使用者輸入轉為結構化 JSON
"""

import json
import os
import anthropic

# 系統提示：指示 Claude 抽取監控條件並以純 JSON 回傳
SYSTEM_PROMPT = """你是一個台股監控條件解析助理。
從使用者的自然語言輸入中，抽取以下欄位並以 JSON 格式回傳。
無法確定的欄位一律回傳 null，絕對不要猜測。

回傳格式（只回傳 JSON，不要其他文字）：
{
  "stock_id": "股票代號，例如 3312（字串）",
  "stock_name": "股票名稱，例如 弘憶",
  "total_shares": 持股股數（整數，1張=1000股），
  "cost_price": 均價（浮點數），
  "stop_loss_moving": 停損價（浮點數），
  "target_stage_1": 第一目標價（浮點數），
  "target_stage_2": 第二目標價（浮點數）
}

範例輸入：「我買了弘憶 5 張，均價 64.86，停損 63，目標 75」
範例輸出：
{
  "stock_id": "3312",
  "stock_name": "弘憶",
  "total_shares": 5000,
  "cost_price": 64.86,
  "stop_loss_moving": 63.0,
  "target_stage_1": 75.0,
  "target_stage_2": null
}
"""

# 全 null 結果範本，API 失敗時使用
_NULL_RESULT = {
    "stock_id": None,
    "stock_name": None,
    "total_shares": None,
    "cost_price": None,
    "stop_loss_moving": None,
    "target_stage_1": None,
    "target_stage_2": None,
}


def parse_monitor_intent(text: str) -> dict:
    """
    解析使用者自然語言輸入，回傳結構化監控參數。

    Args:
        text: 使用者輸入的自然語言字串

    Returns:
        dict，包含 7 個欄位，無法確定的欄位為 None
        API 失敗或 JSON 解析失敗時回傳全 None 的 dict
    """
    # 確認 API 金鑰存在，缺少時提前回傳空結果避免無謂的網路呼叫
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[警告] 未設定 ANTHROPIC_API_KEY，回傳空結果")
        return dict(_NULL_RESULT)

    try:
        # 建立 Anthropic 客戶端並送出解析請求
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        # 取出回應文字，去除首尾空白後解析為 JSON
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        # 確保只回傳已知的欄位，防止 Claude 加入多餘的鍵值污染下遊邏輯
        return {k: result.get(k) for k in _NULL_RESULT}
    except Exception:
        # 任何例外（網路錯誤、JSON 解析失敗等）一律回傳全 null，不讓主程式崩潰
        return dict(_NULL_RESULT)
