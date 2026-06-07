"""
fugle_client.py — Fugle API 統一封裝
整合所有 Fugle REST API 呼叫，提供清潔的介面
當 Fugle API 不可用時，回退到 mock 資料（測試用）
"""

import os
from typing import Optional, Dict

import requests
import pandas as pd

try:
    from mock_stocks import MOCK_STOCKS, MOCK_QUOTES
    MOCK_AVAILABLE = True
except ImportError:
    MOCK_AVAILABLE = False
    MOCK_STOCKS = {}
    MOCK_QUOTES = {}


class FugleClient:
    """Fugle API 統一客戶端"""

    def __init__(self):
        self.api_key = os.environ.get("FUGLE_API_KEY", "")
        self.base_url = "https://api.fugle.tw/v0"
        self._stock_map = None  # 快取股票清單

    def get_quote(self, stock_id: str) -> Optional[Dict]:
        """
        取得股票即時報價。
        回傳 {"stock_id": "2330", "stock_name": "台積電", "close_price": 920.0, "change_pct": -0.84}
        或 None（失敗）
        """
        try:
            url = f"{self.base_url}/intraday/quote?symbolId={stock_id}&apiToken={self.api_key}"
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            info = data.get("data", {}).get("info", {})
            quote = data.get("data", {}).get("quote", {})

            return {
                "stock_id": stock_id,
                "stock_name": info.get("name", ""),
                "close_price": float(quote.get("closePrice", 0)),
                "change_pct": float(quote.get("changePercent", 0)),
            }
        except Exception as e:
            print(f"[fugle] get_quote {stock_id} 失敗：{e}，改用 mock 資料")
            # 回退到 mock 資料
            if MOCK_AVAILABLE and stock_id in MOCK_QUOTES:
                return MOCK_QUOTES[stock_id]
            return None

    def verify_stock(self, stock_id_or_name: str) -> Optional[Dict]:
        """
        驗證股票是否存在。優先用代號查，查不到再用名稱搜尋。
        回傳 {"stock_id": "2330", "stock_name": "台積電"} 或 None
        """
        # 先試用代號查
        try:
            url = f"{self.base_url}/intraday/quote?symbolId={stock_id_or_name}&apiToken={self.api_key}"
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            name = data.get("data", {}).get("info", {}).get("name", "")
            if name:
                return {"stock_id": stock_id_or_name, "stock_name": name}
        except Exception:
            pass

        # 再試用名稱搜尋
        try:
            stock_map = self.load_stock_map()
            if stock_id_or_name in stock_map:
                return {
                    "stock_id": stock_map[stock_id_or_name],
                    "stock_name": stock_id_or_name,
                }
        except Exception:
            pass

        # 回退到 mock 資料
        if MOCK_AVAILABLE:
            if stock_id_or_name in MOCK_STOCKS:
                value = MOCK_STOCKS[stock_id_or_name]
                if isinstance(value, dict):
                    return value
                else:
                    # 是代號，查詢名稱
                    for name, code in MOCK_STOCKS.items():
                        if isinstance(code, str) and code == value:
                            return {"stock_id": code, "stock_name": name}

        return None

    def fetch_candles(self, stock_id: str, days: int = 60) -> pd.DataFrame:
        """
        取得股票日 K 資料。
        回傳 DataFrame with columns: date, open, high, low, close, volume
        """
        try:
            url = (
                f"https://api.fugle.tw/realtime/download/"
                f"historicalCandles?symbol={stock_id}&timeframe=D&limit={days}&apiToken={self.api_key}"
            )
            df = pd.read_csv(url)
            return df
        except Exception as e:
            print(f"[fugle] fetch_candles {stock_id} 失敗：{e}")
            raise

    def load_stock_map(self) -> Dict[str, str]:
        """
        載入全市場股票清單（名稱→代號）。
        快取結果避免重複下載。
        若 Fugle API 失敗，回退到 mock 資料。
        """
        if self._stock_map is not None:
            return self._stock_map

        try:
            # TWSE 上市股票
            twse_url = (
                "https://api.fugle.tw/realtime/download/"
                "tse?apiToken=" + self.api_key
            )
            twse_df = pd.read_csv(twse_url)
            twse_map = dict(zip(twse_df["name"], twse_df["code"]))

            # TPEx 上櫃股票
            tpex_url = (
                "https://api.fugle.tw/realtime/download/"
                "otc?apiToken=" + self.api_key
            )
            tpex_df = pd.read_csv(tpex_url)
            tpex_map = dict(zip(tpex_df["name"], tpex_df["code"]))

            # 合併
            self._stock_map = {**twse_map, **tpex_map}
            return self._stock_map
        except Exception as e:
            print(f"[fugle] load_stock_map 失敗：{e}，改用 mock 資料")
            # 回退到 mock 資料
            if MOCK_AVAILABLE:
                mock_map = {}
                for key, value in MOCK_STOCKS.items():
                    if isinstance(value, str):
                        # key 是名稱，value 是代號
                        mock_map[key] = value
                self._stock_map = mock_map
                return self._stock_map
            return {}
