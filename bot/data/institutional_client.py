"""
institutional_client.py — FinMind 三大法人資料封裝
供盤前/盤後分析注入籌碼面訊號使用
"""

import os
from typing import Optional, Dict
from datetime import date, timedelta
from collections import defaultdict

import requests


def get_institutional_data(stock_id: str, days: int = 5) -> Optional[Dict]:
    """
    取得三大法人近 N 日買賣超資料。

    回傳 {
        "foreign_net": float,      # 外資近 N 日淨買超（張）
        "trust_net": float,        # 投信近 N 日淨買超（張）
        "dealer_net": float,       # 自營商淨買超（張）
        "consecutive_days": int    # 外資+投信合計連續淨買超天數
    }
    或 None（失敗）
    """
    api_key = os.environ.get("FINMIND_API_KEY", "")
    if not api_key:
        return None

    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        start_date = (date.today() - timedelta(days=30)).isoformat()
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": stock_id,
            "api_key": api_key,
            "start_date": start_date,
        }
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        records = resp.json().get("data", [])

        if not records:
            return None

        by_date = defaultdict(lambda: {"foreign": 0.0, "trust": 0.0, "dealer": 0.0})
        for rec in records:
            d = rec["date"]
            net = float(rec.get("buy", 0)) - float(rec.get("sell", 0))
            name = rec.get("name", "")
            if "Foreign_Investor" in name:
                by_date[d]["foreign"] += net
            elif "Investment_Trust" in name:
                by_date[d]["trust"] += net
            elif "Dealer" in name:
                by_date[d]["dealer"] += net

        sorted_dates = sorted(by_date.keys(), reverse=True)[:days]

        foreign_net = sum(by_date[d]["foreign"] for d in sorted_dates)
        trust_net = sum(by_date[d]["trust"] for d in sorted_dates)
        dealer_net = sum(by_date[d]["dealer"] for d in sorted_dates)

        consecutive_days = 0
        for d in sorted_dates:
            if by_date[d]["foreign"] + by_date[d]["trust"] > 0:
                consecutive_days += 1
            else:
                break

        return {
            "foreign_net": foreign_net,
            "trust_net": trust_net,
            "dealer_net": dealer_net,
            "consecutive_days": consecutive_days,
        }
    except Exception as e:
        print(f"[institutional] {stock_id} 法人資料取得失敗：{e}")
        return None


def format_institutional(data: Optional[Dict]) -> str:
    """
    將 get_institutional_data 回傳值格式化為 AI prompt 用文字。
    """
    if not data:
        return "三大法人資料暫無"

    def fmt(val: float) -> str:
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:,.0f}"

    lines = [
        f"外資：{fmt(data['foreign_net'])} 張（近5日）",
        f"投信：{fmt(data['trust_net'])} 張（近5日）",
        f"自營商：{fmt(data['dealer_net'])} 張（近5日）",
        f"連續買超：{data['consecutive_days']} 日",
    ]
    return "\n".join(lines)
