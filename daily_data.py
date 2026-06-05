"""
daily_data.py — 富果 REST 日 K 抓取模組
使用 RestClient 取得歷史收盤資料，回傳 pandas DataFrame
"""

import os
from datetime import date, timedelta

import pandas as pd
from fugle_marketdata import RestClient


def fetch_candles(symbol: str, days: int = 60) -> pd.DataFrame:
    """
    抓取指定股票最近 N 個交易日的日 K。

    Args:
        symbol: 股票代號，例如 "3312"
        days:   抓取天數（日曆天，實際交易日會少於此數）

    Returns:
        DataFrame，欄位：date, open, high, low, close, volume
        依 date 升冪排序（最舊在前）

    Raises:
        RuntimeError: API Key 未設定、或無法取得資料
    """
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=days)).isoformat()

    try:
        # 從環境變數讀取 API Key，傳入 RestClient；
        # 未設定時 api_key 為 None，真實 RestClient 會在 HTTP 請求時拋出認證錯誤
        api_key = os.environ.get("FUGLE_API_KEY")
        client = RestClient(api_key=api_key)
        resp = client.stock.historical.candles(
            symbol=symbol,
            from_=start_date,
            to=end_date,
            fields="open,high,low,close,volume",
        )
        raw = resp.get("data", [])
    except Exception as e:
        raise RuntimeError(f"無法取得 {symbol} 日 K 資料：{e}") from e

    if not raw:
        raise RuntimeError(f"無法取得 {symbol} 日 K 資料：回傳為空")

    df = pd.DataFrame(raw, columns=["date", "open", "high", "low", "close", "volume"])
    df = df.sort_values("date").reset_index(drop=True)
    return df
