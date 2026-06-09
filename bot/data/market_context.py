"""
market_context.py — 盤前市場背景資料抓取
抓取美股指數、台指期夜盤、匯率、VIX，供盤前分析使用
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 指數代號
_SYMBOLS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "sox": "^SOX",
    "vix": "^VIX",
    "tsm_adr": "TSM",
    "usd_twd": "USDTWD=X",
    "tw_index": "^TWII",    # 台灣加權指數（Yahoo Finance 不提供夜期，以此替代）
}


def fetch_market_context() -> Optional[Dict[str, Any]]:
    """
    抓取盤前市場背景資料。
    回傳 dict 或 None（完全失敗時）。
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("[market_context] yfinance 未安裝，跳過市場背景")
        return None

    result = {}
    for key, symbol in _SYMBOLS.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d", interval="1d")
            if hist.empty:
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
            logger.warning("[market_context] {} 抓取失敗：{}".format(symbol, e))

    if not result:
        return None

    result["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return result


def format_market_context(ctx: Dict[str, Any]) -> str:
    """
    將市場背景資料格式化為 AI prompt 用的文字段落。
    """
    if not ctx:
        return ""

    lines = ["【今日盤前市場背景】"]

    def _fmt(key: str, label: str, unit: str = "") -> None:
        entry = ctx.get(key)
        if not entry:
            return
        price = entry["price"]
        chg = entry.get("change_pct")
        if chg is not None:
            arrow = "▲" if chg >= 0 else "▼"
            lines.append(f"{label}：{price}{unit}  {arrow}{abs(chg):.2f}%")
        else:
            lines.append(f"{label}：{price}{unit}")

    _fmt("sp500",    "S&P 500")
    _fmt("nasdaq",   "Nasdaq")
    _fmt("sox",      "費城半導體（SOX）")
    _fmt("tsm_adr",  "TSM ADR（台積電美股）", " USD")
    _fmt("vix",      "VIX 恐慌指數")
    _fmt("usd_twd",  "美元/台幣匯率")
    _fmt("tw_index", "台灣加權指數（昨收）")

    fetched_at = ctx.get("fetched_at", "")
    if fetched_at:
        lines.append(f"（資料截至 {fetched_at}）")

    return "\n".join(lines)
