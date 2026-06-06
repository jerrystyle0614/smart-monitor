"""
claude_parser.py — 自然語言監控條件解析模組
呼叫 Claude API 一次，將使用者輸入轉為結構化 JSON
"""

import json
import os
import requests
import anthropic
from google import genai as google_genai

# 股票名稱→代號對照表，啟動時從 Fugle 載入
_STOCK_MAP: dict[str, str] = {}  # {名稱: 代號}


def load_stock_map() -> None:
    """從 Fugle API 載入上市(TWSE)和上櫃(TPEx)的完整股票清單，建立名稱→代號對照表"""
    global _STOCK_MAP
    api_key = os.environ.get("FUGLE_API_KEY")
    if not api_key:
        print("[警告] 未設定 FUGLE_API_KEY，股票名稱查詢將無法使用")
        return
    combined = {}
    for exchange in ("TWSE", "TPEx"):
        try:
            r = requests.get(
                f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/tickers",
                headers={"X-API-KEY": api_key},
                params={"type": "EQUITY", "exchange": exchange},
                timeout=15,
            )
            if r.status_code == 200:
                for item in r.json().get("data", []):
                    name = item.get("name", "").strip()
                    symbol = item.get("symbol", "").strip()
                    if name and symbol:
                        combined[name] = symbol
        except Exception as e:
            print(f"[警告] 載入 {exchange} 股票清單失敗：{e}")
    _STOCK_MAP = combined
    print(f"[stock_map] 已載入 {len(_STOCK_MAP)} 筆股票資料")

# 系統提示：指示 Claude 抽取監控條件並以純 JSON 回傳
# 輸入字數上限（超過截斷，避免長訊息耗費大量 token）
INPUT_MAX_CHARS = 200

# 非監控意圖的閒聊回覆 token 上限
CHAT_MAX_TOKENS = 80

INTENT_SYSTEM_PROMPT = """判斷使用者的訊息是否為「設定股票監控條件」的意圖。
只回傳 true 或 false，不要其他文字。

屬於監控意圖的例子（回傳 true）：
- 「我買了弘憶 5 張，成本 64.86」
- 「幫我監控台積電，停損 900」
- 「3312 弘憶，5張，均價64.86」
- 「弘憶5張，成本在64.86」
- 「我有持股想設定通知」

不屬於監控意圖的例子（回傳 false）：
- 「今天天氣真好」
- 「你好」
- 「謝謝」
- 「幫我查一下台積電股價」
"""

SYSTEM_PROMPT = """你是一個台股監控條件解析助理。
從使用者的自然語言輸入中，抽取以下欄位並以 JSON 格式回傳。
無法確定的欄位一律回傳 null，絕對不要猜測。
stock_id 規則：如果使用者直接說代號（如 3312、0050、0056）就用那個；台股代號固定為 4~6 位數字，ETF 代號通常為 4~6 位（如 0050、0056、00878）；如果只說股票名稱（如弘憶、台積電、鴻海），請根據你的台股知識填入對應代號；真的不確定才回傳 null。
stock_name 規則：只要知道 stock_id 對應的名稱，就必須填入 stock_name，例如 0056 → 元大高股息、0050 → 元大台灣50、2330 → 台積電；不要回傳 null。
張數斷詞規則：代號後面緊接數字和「張」時，代號本身不含「張」前面的數字，例如「00561張」應解析為代號 0056、張數 1。
停損價格：直接使用使用者說的數字填入 stop_loss_moving，不論高低，不要自動移到其他欄位。

回傳格式（只回傳純 JSON，不要 markdown、不要 ```json、不要任何說明文字）：
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

# Claude 閒聊失敗時的備用訊息
HELP_FALLBACK = "輸入你的持股狀況即可開始監控，例如：「我買了弘憶 5 張，均價 64.86，停損 63 元」"

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


def _truncate(text: str) -> str:
    """截斷過長輸入，超過 INPUT_MAX_CHARS 的部分直接丟棄"""
    if len(text) > INPUT_MAX_CHARS:
        print(f"[警告] 輸入超過 {INPUT_MAX_CHARS} 字，已截斷")
        return text[:INPUT_MAX_CHARS]
    return text


def is_monitor_intent(text: str) -> bool:
    """
    用 Gemini 判斷使用者訊息是否為設定監控條件的意圖（免費額度）。
    API 失敗時預設回傳 False（不觸發解析）。
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return False

    try:
        client = google_genai.Client(api_key=api_key)
        prompt = f"{INTENT_SYSTEM_PROMPT}\n\n使用者訊息：{_truncate(text)}"
        response = client.models.generate_content(
            model="models/gemini-2.5-flash-lite",
            contents=prompt,
        )
        raw = response.text.strip().lower()
        print(f"[Gemini 意圖判斷] {raw}")
        return raw == "true"
    except Exception as e:
        print(f"[警告] Gemini 意圖判斷失敗：{e}")
        return False


def chat_reply(text: str) -> str:
    """
    非監控意圖的閒聊回覆。
    回覆限制在 CHAT_MAX_TOKENS token 內，失敗時回傳預設說明訊息。
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return HELP_FALLBACK

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=CHAT_MAX_TOKENS,
            system=(
                "你是一個友善的台股監控助理，名叫 Smart Monitor。"
                "用繁體中文簡短回覆使用者，不超過 50 字。"
                "如果使用者問的問題超出股票監控範疇，"
                "禮貌地說明你主要負責股票監控設定，並引導他輸入持股條件。"
            ),
            messages=[{"role": "user", "content": _truncate(text)}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[警告] Claude 閒聊回覆失敗：{e}")
        return HELP_FALLBACK


def parse_monitor_intent(text: str) -> dict:
    """
    用 Gemini 解析使用者自然語言輸入，回傳結構化監控參數。
    API 失敗或 JSON 解析失敗時回傳全 None 的 dict。
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[警告] 未設定 GEMINI_API_KEY，回傳空結果")
        return dict(_NULL_RESULT)

    try:
        client = google_genai.Client(api_key=api_key)
        prompt = f"{SYSTEM_PROMPT}\n\n使用者輸入：{_truncate(text)}"
        response = client.models.generate_content(
            model="models/gemini-2.5-flash-lite",
            contents=prompt,
        )
        raw = response.text.strip()
        # 去除 Gemini 有時回傳的 markdown 包裝（```json ... ```）
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        print(f"[Gemini 解析] {raw}")
        result = json.loads(raw)
        parsed = {k: result.get(k) for k in _NULL_RESULT}

        # 用 Fugle 對照表驗證 stock_id，若 AI 猜錯就用名稱重新查
        parsed = _verify_stock(parsed)
        return parsed
    except Exception as e:
        print(f"[警告] Gemini 解析失敗：{e}")
        return dict(_NULL_RESULT)


def _verify_stock(parsed: dict) -> dict:
    """
    用 Fugle 對照表驗證 stock_id。
    規則：
    1. stock_id 在對照表中存在 → 保留代號和使用者輸入的名稱（不覆蓋）
    2. stock_id 不在對照表，但名稱完全吻合 → 補上正確代號
    3. 其他情況 → 保留原值，讓使用者自行確認或修改
    注意：不做部分名稱比對，避免「事欣」誤命中「新唐」等不相關股票
    """
    stock_id = parsed.get("stock_id")
    stock_name = parsed.get("stock_name")
    reverse_map = {v: k for k, v in _STOCK_MAP.items()}

    # 代號在 Fugle 對照表中存在 → 代號正確，保留使用者輸入的名稱不覆蓋
    if stock_id and stock_id in reverse_map:
        print(f"[verify_stock] 代號 {stock_id} 已驗證")
        return parsed

    # 代號不存在或為 null，且名稱完全吻合 → 補上代號
    if stock_name and stock_name in _STOCK_MAP:
        parsed["stock_id"] = _STOCK_MAP[stock_name]
        print(f"[verify_stock] 用名稱補代號：{stock_name} → {parsed['stock_id']}")
        return parsed

    # 找不到，保留原值讓使用者確認（不強制設為 null）
    print(f"[verify_stock] 無法驗證：{stock_id} {stock_name}，保留原值")
    return parsed
