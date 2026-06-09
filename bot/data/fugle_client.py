"""
fugle_client.py — Fugle API 統一封裝
整合所有 Fugle REST API 呼叫，提供清潔的介面
當 Fugle API 不可用時，回退到 mock 資料（測試用）
"""

import os
import base64
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
        # Fugle API Key 直接使用環境變數值（Base64 格式），不需解碼
        self.api_key = os.environ.get("FUGLE_API_KEY", "")

        # 使用正確的 Fugle marketdata v1.0 API
        self.base_url = "https://api.fugle.tw/marketdata/v1.0"
        self._stock_map = None  # 快取股票清單

    def get_quote(self, stock_id: str) -> Optional[Dict]:
        """
        取得股票即時報價。
        回傳 {"stock_id": "2330", "stock_name": "台積電", "close_price": 920.0, "change_pct": -0.84}
        或 None（失敗）
        """
        try:
            # 使用 marketdata v1.0 API
            url = f"{self.base_url}/stock/intraday/quote/{stock_id}"
            headers = {"X-API-KEY": self.api_key}

            resp = requests.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            # marketdata v1.0 的回應格式是扁平的，不是嵌套的
            return {
                "stock_id": stock_id,
                "stock_name": data.get("name", ""),
                "close_price": float(data.get("closePrice", 0)),
                "change_pct": float(data.get("changePercent", 0)),
            }
        except Exception as e:
            # 回退到 mock 資料（靜默處理，不顯示錯誤）
            if MOCK_AVAILABLE and stock_id in MOCK_QUOTES:
                return MOCK_QUOTES[stock_id]
            print(f"[fugle] get_quote {stock_id} 失敗：{e}")
            return None

    def verify_stock(self, stock_id_or_name: str) -> Optional[Dict]:
        """
        驗證股票是否存在。優先用代號查，查不到再用名稱搜尋。
        回傳 {"stock_id": "2330", "stock_name": "台積電"} 或 None
        """
        # 先試用代號查
        try:
            url = f"{self.base_url}/stock/intraday/quote/{stock_id_or_name}"
            headers = {"X-API-KEY": self.api_key}

            resp = requests.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            # 如果能成功查詢，則該股票存在
            name = data.get("name", stock_id_or_name)
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

    def fetch_candles(self, stock_id: str, days: int = 60, premarket: bool = False) -> pd.DataFrame:
        """
        取得股票日 K 資料（官方 fugle_marketdata SDK，historical/candles）。

        注意：歷史日 K 端點通常落後一個交易日（盤後當日資料尚未入庫），
        因此預設會用即時報價補上今日 K 線（盤後適用）。
        盤前分析（premarket=True）時不補今日，避免帶入尚未成交完的量。

        回傳 DataFrame with columns: date, open, high, low, close, volume
        """
        from datetime import date, timedelta
        from fugle_marketdata import RestClient

        api_key = os.environ.get("FUGLE_API_KEY", "")
        if not api_key:
            print("[fugle] 無 FUGLE_API_KEY，無法取得 K 線資料")
            return None

        try:
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=days)).isoformat()

            client = RestClient(api_key=api_key)
            resp = client.stock.historical.candles(
                symbol=stock_id,
                from_=start_date,
                to=end_date,
                fields="open,high,low,close,volume",
            )
            raw = resp.get("data", [])
            if not raw:
                print(f"[fugle] fetch_candles {stock_id} 歷史日 K 回傳為空")
                return None

            df = pd.DataFrame(
                raw, columns=["date", "open", "high", "low", "close", "volume"]
            )
            df = df.sort_values("date").reset_index(drop=True)

            # 盤後才補今日 K 線；盤前跳過，避免帶入不完整的當日成交量
            if not premarket:
                df = self._append_today_candle(stock_id, df)

            print(
                f"[fugle] fetch_candles {stock_id} 取得 {len(df)} 筆，"
                f"最後一筆 {df.iloc[-1]['date']} 收盤 {df.iloc[-1]['close']}"
            )
            return df
        except Exception as e:
            print(f"[fugle] fetch_candles {stock_id} 失敗：{e}")
            raise

    def _append_today_candle(self, stock_id: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        若歷史日 K 的最後一筆不是今日，且即時報價已有今日成交，
        則將今日 K 線（用即時報價組成）接到 DataFrame 尾端。
        """
        try:
            from datetime import date

            url = f"{self.base_url}/stock/intraday/quote/{stock_id}"
            resp = requests.get(
                url, headers={"X-API-KEY": self.api_key}, timeout=5
            )
            resp.raise_for_status()
            q = resp.json()

            quote_date = q.get("date")
            today = date.today().isoformat()
            close_price = q.get("closePrice") or q.get("lastPrice")

            # 即時報價非今日、無收盤、或歷史已含今日 → 不補
            if quote_date != today or close_price is None:
                return df
            if len(df) > 0 and str(df.iloc[-1]["date"]) == today:
                return df

            today_row = {
                "date": today,
                "open": float(q.get("openPrice", close_price)),
                "high": float(q.get("highPrice", close_price)),
                "low": float(q.get("lowPrice", close_price)),
                "close": float(close_price),
                "volume": int(q.get("total", {}).get("tradeVolume", 0))
                if isinstance(q.get("total"), dict)
                else 0,
            }
            print(f"[fugle] {stock_id} 補上今日即時 K 線：收盤 {close_price}")
            return pd.concat(
                [df, pd.DataFrame([today_row])], ignore_index=True
            )
        except Exception as e:
            print(f"[fugle] {stock_id} 補今日 K 線失敗（忽略）：{e}")
            return df

    def load_stock_map(self) -> Dict[str, str]:
        """
        載入全市場股票清單（名稱→代號）。
        使用 marketdata v1.0 的 tickers 端點（上市 TWSE + 上櫃 TPEx）。
        快取結果避免重複下載。
        若 Fugle API 失敗，回退到 mock 資料。
        """
        if self._stock_map is not None:
            return self._stock_map

        try:
            stock_map = {}
            headers = {"X-API-KEY": self.api_key}
            # 上市 TWSE + 上櫃 TPEx，合併為單一「名稱→代號」對照表
            for exchange in ("TWSE", "TPEx"):
                url = f"{self.base_url}/stock/intraday/tickers"
                params = {
                    "type": "EQUITY",
                    "exchange": exchange,
                    "isNormal": "true",
                }
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                resp.raise_for_status()
                for item in resp.json().get("data", []):
                    name = str(item.get("name", "")).strip()
                    symbol = str(item.get("symbol", "")).strip()
                    if name and symbol:
                        stock_map[name] = symbol

            if not stock_map:
                raise ValueError("tickers 回傳為空")

            self._stock_map = stock_map
            return self._stock_map
        except Exception as e:
            # 回退到 mock 資料（靜默處理）
            if MOCK_AVAILABLE:
                mock_map = {}
                for key, value in MOCK_STOCKS.items():
                    if isinstance(value, str):
                        # key 是名稱，value 是代號
                        mock_map[key] = value
                self._stock_map = mock_map
                return self._stock_map
            print(f"[fugle] load_stock_map 失敗：{e}")
            return {}
