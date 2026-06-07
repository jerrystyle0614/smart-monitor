"""
fugle_client.py — Fugle API 統一封裝
整合所有 Fugle REST API 呼叫，提供清潔的介面
"""

import os
from typing import Optional, Dict

import requests
import pandas as pd


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
            print(f"[fugle] get_quote {stock_id} 失敗：{e}")
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
            print(f"[fugle] load_stock_map 失敗：{e}")
            return {}
