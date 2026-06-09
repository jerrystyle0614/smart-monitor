"""
finmind_client.py — FinMind API 統一封裝
取得籌碼面資料：三大法人買賣超、融資融券
"""

import os
from typing import Optional, Dict, List
from datetime import datetime, timedelta

import requests


class FinMindClient:
    """
    FinMind API 客戶端

    注意：當前 get_three_major_buyers 和 get_margin_status 返回 API 錯誤
    原因待確認：dataset 名稱或參數格式可能不符合最新 FinMind API
    TODO: 驗證正確的 dataset 名稱
    """

    def __init__(self):
        self.api_key = os.environ.get("FINMIND_API_KEY", "")
        self.base_url = "https://api.finmindtrade.com/api/v4"

    def get_three_major_buyers(self, stock_id: str, days: int = 5) -> Optional[Dict]:
        """
        取得三大法人買賣超資料。
        Dataset: TaiwanStockInstitutionalInvestorsBuySell（免費方案可用）
        name 欄位值：Foreign_Investor / Investment_Trust / Dealer_self / Dealer_Hedging

        回傳 {
            "consecutive_net_buy_days": int,   # 外資+投信合計連續淨買超天數
            "foreign_net": float,              # 外資近 days 日淨買超
            "trust_net": float,                # 投信近 days 日淨買超
            "total_net": float,                # 三大法人合計淨買超
            "dates": list                      # 涵蓋的日期
        }
        或 None（失敗）
        """
        from datetime import date, timedelta
        try:
            url = f"{self.base_url}/data"
            start_date = (date.today() - timedelta(days=30)).isoformat()
            params = {
                "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
                "data_id": stock_id,
                "api_key": self.api_key,
                "start_date": start_date,
            }
            resp = requests.get(url, params=params, timeout=8)
            resp.raise_for_status()
            records = resp.json().get("data", [])

            if not records:
                return None

            # 依日期聚合
            from collections import defaultdict
            by_date = defaultdict(lambda: {"foreign": 0, "trust": 0, "dealer": 0})
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
            total_net = foreign_net + trust_net + dealer_net

            # 計算外資+投信合計連續淨買超天數
            consecutive_days = 0
            for d in sorted_dates:
                if by_date[d]["foreign"] + by_date[d]["trust"] > 0:
                    consecutive_days += 1
                else:
                    break

            # 計算投信單獨連續淨買超天數
            trust_consecutive = 0
            for d in sorted_dates:
                if by_date[d]["trust"] > 0:
                    trust_consecutive += 1
                else:
                    break

            return {
                "consecutive_net_buy_days": consecutive_days,
                "foreign_net": foreign_net,
                "trust_net": trust_net,
                "dealer_net": dealer_net,
                "total_net": total_net,
                "trust_consecutive_days": trust_consecutive,
                "dates": sorted_dates,
            }
        except Exception as e:
            print(f"[finmind] get_three_major_buyers {stock_id} 失敗：{e}")
            return None

    def get_margin_status(self, stock_id: str) -> Optional[Dict]:
        """
        取得融資融券狀態。
        使用 FinMind API: TaiwanDailyShortSaleBalances dataset
        回傳 {
            "margin_balance": float,
            "short_balance": float,
            "margin_increase_pct": float,
            "date": str
        }
        或 None（失敗或資料不足）

        API Verification Result (2026-06-07):
        ✓ TaiwanDailyShortSaleBalances: WORKING
        - Parameters: data_id (not stock_id), start_date
        - Returns: MarginShortSalesCurrentDayBalance, SBLShortSalesCurrentDayBalance, etc.
        """
        try:
            url = f"{self.base_url}/data"
            params = {
                "dataset": "TaiwanDailyShortSaleBalances",
                "data_id": stock_id,
                "api_key": self.api_key,
                "start_date": "2026-06-01",
            }
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("data"):
                return None

            records = data.get("data", [])
            if len(records) < 1:
                return None

            current = records[0]

            # TaiwanDailyShortSaleBalances 回傳的欄位
            margin_balance = float(current.get("MarginShortSalesCurrentDayBalance", 0))
            short_balance = float(current.get("SBLShortSalesCurrentDayBalance", 0))

            # 計算增幅：比對前一天資料
            margin_increase_pct = 0
            if len(records) > 1:
                previous = records[1]
                margin_previous = float(previous.get("MarginShortSalesCurrentDayBalance", 0))
                if margin_previous > 0:
                    margin_increase_pct = (margin_balance - margin_previous) / margin_previous * 100

            return {
                "margin_balance": margin_balance,
                "short_balance": short_balance,
                "margin_increase_pct": margin_increase_pct,
                "date": current.get("date"),
            }
        except Exception as e:
            print(f"[finmind] get_margin_status {stock_id} 失敗：{e}")
            return None

    def get_all_stocks_basic(self) -> List[Dict]:
        """
        取得全市場股票基本資訊。
        回傳 [{"stock_id": "2330", "stock_name": "台積電"}, ...]
        """
        try:
            url = f"{self.base_url}/data"
            params = {
                "dataset": "TaiwanStockInfo",
                "api_key": self.api_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            return data.get("data", [])
        except Exception as e:
            print(f"[finmind] get_all_stocks_basic 失敗：{e}")
            return []
