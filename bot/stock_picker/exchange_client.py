"""
exchange_client.py — 台股資料統一封裝
- 股票清單：FinMind TaiwanStockInfo
- 融資融券：FinMind TaiwanDailyShortSaleBalances
- 三大法人：TEJ API（試用中）
"""

from typing import Optional, Dict, List
import os
import requests
from datetime import datetime, timedelta


class ExchangeClient:
    """
    台股資料統一客戶端
    支援多個資料來源：FinMind（股票清單、融資融券）+ TEJ（三大法人）
    """

    def __init__(self):
        self.finmind_api_key = os.environ.get("FINMIND_API_KEY", "")
        self.finmind_base = "https://api.finmindtrade.com/api/v4"
        self.tej_api_key = os.environ.get("TEJ_API_KEY", "")
        self.tej_base = "https://api.tej.com.tw"

    def get_three_major_buyers(self, stock_id: str, days: int = 3) -> Optional[Dict]:
        """
        取得三大法人買賣超資料。
        優先嘗試 TEJ API；失敗則返回 None
        """
        if self.tej_api_key:
            result = self._fetch_tej_three_major(stock_id, days)
            if result:
                return result

        print(f"[exchange_client] {stock_id} 三大法人資料暫不可用（TEJ API 驗證中）")
        return None

    def _fetch_tej_three_major(self, stock_id: str, days: int = 3) -> Optional[Dict]:
        """
        從 TEJ API 取得三大法人買賣超。
        端點：/api/v1/stock/{symbol}/institutional
        """
        try:
            # 使用前一個交易日
            target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            url = f"{self.tej_base}/api/v1/stock/{stock_id}/institutional"
            params = {
                "apikey": self.tej_api_key,
                "date": target_date,
            }

            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            if not data or not data.get("data"):
                return None

            records = data.get("data", [])
            if len(records) == 0:
                return None

            latest = records[0]

            # TEJ 回傳格式：外資買/賣、投信買/賣、自營買/賣
            foreign_buy = float(latest.get("foreign_buy", 0))
            foreign_sell = float(latest.get("foreign_sell", 0))
            invest_buy = float(latest.get("invest_buy", 0))
            invest_sell = float(latest.get("invest_sell", 0))
            dealer_buy = float(latest.get("dealer_buy", 0))
            dealer_sell = float(latest.get("dealer_sell", 0))

            total_buy = foreign_buy + invest_buy + dealer_buy
            total_sell = foreign_sell + invest_sell + dealer_sell

            net_buy = total_buy - total_sell
            consecutive_days = 1 if net_buy > 0 else 0

            return {
                "consecutive_buy_days": consecutive_days,
                "total_buy": total_buy,
                "total_sell": total_sell,
                "latest_data": {
                    "date": latest.get("date", target_date),
                    "buy": total_buy,
                    "sell": total_sell,
                    "net": net_buy,
                    "foreign": {"buy": foreign_buy, "sell": foreign_sell},
                    "invest": {"buy": invest_buy, "sell": invest_sell},
                    "dealer": {"buy": dealer_buy, "sell": dealer_sell},
                },
                "market": "TWSE/TPEX",
            }

        except Exception as e:
            print(f"[exchange_client] TEJ 查詢 {stock_id} 失敗：{e}")
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
