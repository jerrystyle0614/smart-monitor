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

    def get_three_major_buyers(self, stock_id: str, days: int = 3) -> Optional[Dict]:
        """
        取得三大法人買賣超資料。
        回傳 {
            "consecutive_buy_days": int,
            "total_buy": float,
            "total_sell": float,
            "latest_data": dict or None
        }
        或 None（失敗）
        """
        try:
            url = f"{self.base_url}/data"
            params = {
                "dataset": "TaiwanStockThreeMainForces",
                "stock_id": stock_id,
                "api_key": self.api_key,
            }
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("data"):
                return None

            # 計算連續買超天數
            records = data.get("data", [])
            consecutive_days = 0
            for record in records:
                buy = float(record.get("buy", 0))
                sell = float(record.get("sell", 0))
                if buy > sell:
                    consecutive_days += 1
                else:
                    break

            return {
                "consecutive_buy_days": consecutive_days,
                "total_buy": sum(float(r.get("buy", 0)) for r in records[:days]),
                "total_sell": sum(float(r.get("sell", 0)) for r in records[:days]),
                "latest_data": records[0] if records else None,
            }
        except Exception as e:
            print(f"[finmind] get_three_major_buyers {stock_id} 失敗：{e}")
            return None

    def get_margin_status(self, stock_id: str) -> Optional[Dict]:
        """
        取得融資融券狀態。
        回傳 {
            "margin_balance": float,
            "short_balance": float,
            "margin_increase_pct": float,
            "date": str
        }
        或 None（失敗或資料不足）
        """
        try:
            url = f"{self.base_url}/data"
            params = {
                "dataset": "TaiwanStockMarginPurchaseShortSale",
                "stock_id": stock_id,
                "api_key": self.api_key,
            }
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("data"):
                return None

            records = data.get("data", [])
            if len(records) < 2:
                return None

            current = records[0]
            previous = records[1]

            margin_current = float(current.get("MarginBalance", 0))
            margin_previous = float(previous.get("MarginBalance", 0))

            margin_increase_pct = 0
            if margin_previous > 0:
                margin_increase_pct = (margin_current - margin_previous) / margin_previous * 100

            return {
                "margin_balance": margin_current,
                "short_balance": float(current.get("ShortBalance", 0)),
                "margin_increase_pct": margin_increase_pct,
                "date": current.get("Date"),
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
