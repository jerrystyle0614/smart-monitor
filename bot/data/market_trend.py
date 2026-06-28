"""
market_trend.py — 每日大盤走勢資料抓取與 AI 分析
供 08:50 排程推播使用
"""

import logging
from typing import Optional, Dict, Any

import yfinance as yf
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_SYMBOLS = {
    "sp500":   "^GSPC",
    "nasdaq":  "^IXIC",
    "sox":     "^SOX",
    "tsm_adr": "TSM",
    "vix":     "^VIX",
    "usd_twd": "USDTWD=X",
}

_LABELS = {
    "sp500":   "S&P 500",
    "nasdaq":  "那斯達克",
    "sox":     "費城半導體（SOX）",
    "tsm_adr": "TSM ADR（台積電美股）",
    "vix":     "VIX 恐慌指數",
    "usd_twd": "美元/台幣匯率",
}

_ANALYSIS_PROMPT = """
你是台股投資分析師。根據以下昨日美股及相關指數收盤資料，
用繁體中文給台股投資人今日大盤操作建議。

指數資料：
{market_data}

請提供：
1. 今日台股大盤開盤偏多/偏空/中性的判斷，及理由（1-2句）
2. 今日是否適合積極操作（適合/觀望/避開），及原因（1-2句）
3. 需要特別注意的風險點（1條即可）

格式：3段文字，每段不超過50字，直接給結論，不要廢話。
"""


def fetch_market_data():
    # type: () -> Optional[Dict[str, Any]]
    """
    抓取大盤相關指數昨收資料。
    回傳 dict 或 None（全部失敗時）。
    """
    result = {}
    for key, symbol in _SYMBOLS.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d", interval="1d")
            if hist is None or hist.empty:
                continue
            last = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) >= 2 else None
            close = float(last["Close"])
            change_pct = None
            if prev is not None:
                prev_close = float(prev["Close"])
                if prev_close > 0:
                    change_pct = round((close - prev_close) / prev_close * 100, 2)
            result[key] = {
                "price": round(close, 4) if key == "usd_twd" else round(close, 2),
                "change_pct": change_pct,
            }
        except Exception as e:
            logger.warning("[market_trend] {} 取得失敗：{}".format(symbol, e))

    return result if result else None


def analyze_market_trend(market_data):
    # type: (Dict[str, Any]) -> str
    """
    用 Claude Haiku 分析大盤資料，回傳繁體中文分析文字。
    API 失敗時回傳純數據摘要（不拋例外）。
    """
    lines = []
    for key, label in _LABELS.items():
        entry = market_data.get(key)
        if not entry:
            continue
        price = entry["price"]
        chg = entry.get("change_pct")
        if chg is not None:
            arrow = "▲" if chg >= 0 else "▼"
            lines.append("{}：{}  {}{:.2f}%".format(label, price, arrow, abs(chg)))
        else:
            lines.append("{}：{}".format(label, price))

    market_data_text = "\n".join(lines)

    try:
        client = Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": _ANALYSIS_PROMPT.format(market_data=market_data_text),
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning("[market_trend] Claude 分析失敗，使用純數據摘要：{}".format(e))
        return market_data_text


def build_market_trend_message(ai_analysis, fetched_at):
    # type: (str, str) -> str
    """
    組合完整推播訊息（標題 + AI 分析 + 免責聲明）。
    """
    parts = [
        "📈 今日大盤走勢預測（{}）".format(fetched_at),
        "",
        ai_analysis,
        "",
        "⚠️ 本分析僅供參考，投資決策應自負其責",
    ]
    return "\n".join(parts)
