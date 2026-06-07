"""
exchange_client.py — TWSE/TPEX 融資融券資料與股票清單
(三大法人資料 TWSE OpenAPI 未提供公開個股端點，暫時略過)
"""

from typing import Optional, Dict, List
import os
import requests


class ExchangeClient:
    """
    台股資料統一客戶端
    - 股票清單來源：Fugle API（已在系統中使用）
    - 融資融券資料：FinMind API（已驗證可用）
    - 三大法人：待替代方案（TWSE OpenAPI 不提供個股端點）
    """

    def __init__(self):
        self.finmind_api_key = os.environ.get("FINMIND_API_KEY", "")
        self.finmind_base = "https://api.finmindtrade.com/api/v4"

    def get_three_major_buyers(self, stock_id: str, days: int = 3) -> Optional[Dict]:
        """
        取得三大法人買賣超資料。
        注意：TWSE OpenAPI 未提供個股三大法人查詢端點
        暫時返回 None，等待替代方案
        """
        print(f"[exchange_client] {stock_id} 三大法人資料暫不可用（TWSE 無公開個股端點）")
        return None

    def get_margin_status(self, stock_id: str) -> Optional[Dict]:
        """
        取得融資融券狀態（從 FinMind）。
        回傳 {
            "margin_balance": float,
            "short_balance": float,
            "margin_increase_pct": float,
            "date": str
        }
        或 None（失敗）
        """
        try:
            url = f"{self.finmind_base}/data"
            params = {
                "dataset": "TaiwanDailyShortSaleBalances",
                "data_id": stock_id,
                "api_key": self.finmind_api_key,
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

            margin_balance = float(current.get("MarginShortSalesCurrentDayBalance", 0))
            short_balance = float(current.get("SBLShortSalesCurrentDayBalance", 0))

            # 計算增幅
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
            print(f"[exchange_client] 融資融券查詢 {stock_id} 失敗：{e}")
            return None

    def get_all_stocks_basic(self) -> List[Dict]:
        """
        取得全市場股票基本資訊（從 FinMind）。
        回傳 [{"stock_id": "2330", "stock_name": "台積電"}, ...]
        """
        try:
            url = f"{self.finmind_base}/data"
            params = {
                "dataset": "TaiwanStockInfo",
                "api_key": self.finmind_api_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            print(f"[exchange_client] 股票清單取得失敗：{e}")
            return []
