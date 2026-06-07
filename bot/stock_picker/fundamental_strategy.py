"""
fundamental_strategy.py — 籌碼面篩選策略
篩選條件：融資餘額增幅（FinMind）
"""

import os
from typing import List, Optional, Dict, Any
import requests

from bot.stock_picker.base import Stock, Strategy


class FundamentalStrategy(Strategy):
    """籌碼面策略：融資餘額篩選"""

    def __init__(
        self,
        finmind_client: Optional[Any] = None,
        stock_list_provider: Optional[callable] = None,
        margin_increase_threshold: float = 5.0,
    ):
        """
        Args:
            finmind_client: FinMind API 客戶端（若不提供則自動初始化）
            stock_list_provider: 取得股票清單的函數
            margin_increase_threshold: 融資增幅閾值（%）
        """
        self.name = "fundamental"
        self.finmind_client = finmind_client
        self.stock_list_provider = stock_list_provider
        self.margin_increase_threshold = margin_increase_threshold
        self.finmind_base = "https://api.finmindtrade.com/api/v4"
        self.finmind_api_key = os.environ.get("FINMIND_API_KEY", "")

    def scan(self) -> List[Stock]:
        """
        掃描符合籌碼面條件的股票。
        篩選條件：融資餘額日增幅 < threshold（表示籌碼相對穩定）
        """
        try:
            all_stocks = self.stock_list_provider()
            if not all_stocks:
                print("[fundamental] 股票清單為空")
                return []
        except Exception as e:
            print(f"[fundamental] 無法取得股票清單：{e}")
            return []

        qualified = []

        for stock_data in all_stocks:
            stock_id = stock_data.get("stock_id", "")
            stock_name = stock_data.get("stock_name", "")

            if not stock_id:
                continue

            # 檢查融資餘額增幅
            margin = self._get_margin_status(stock_id)
            if not margin:
                continue

            margin_increase_pct = margin.get("margin_increase_pct", 0)
            if margin_increase_pct >= self.margin_increase_threshold:
                continue

            # 通過篩選
            qualified.append(Stock(stock_id=stock_id, stock_name=stock_name))

        return qualified

    def _get_margin_status(self, stock_id: str) -> Optional[Dict[str, Any]]:
        """從 FinMind 取得融資餘額資料"""
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

            # 計算增幅
            margin_increase_pct = 0
            if len(records) > 1:
                previous = records[1]
                margin_previous = float(previous.get("MarginShortSalesCurrentDayBalance", 0))
                if margin_previous > 0:
                    margin_increase_pct = (margin_balance - margin_previous) / margin_previous * 100

            return {
                "margin_balance": margin_balance,
                "margin_increase_pct": margin_increase_pct,
                "date": current.get("date"),
            }
        except Exception as e:
            return None
