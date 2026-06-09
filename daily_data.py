"""
daily_data.py — 富果 REST 日 K 抓取模組
使用 RestClient 取得歷史收盤資料，回傳 pandas DataFrame
"""

import os
from datetime import date, timedelta

import pandas as pd
from fugle_marketdata import RestClient


def fetch_candles(symbol: str, days: int = 60, premarket: bool = False) -> pd.DataFrame:
    """
    抓取指定股票最近 N 個交易日的日 K。

    Args:
        symbol:     股票代號，例如 "3312"
        days:       抓取天數（日曆天，實際交易日會少於此數）
        premarket:  True 時跳過補今日 K 線，避免帶入盤前不完整的成交量

    Returns:
        DataFrame，欄位：date, open, high, low, close, volume
        依 date 升冪排序（最舊在前）

    Raises:
        RuntimeError: API Key 未設定、或無法取得資料
    """
    # 早期防守：未設定 API Key 時立即拋出，不進入網路呼叫
    api_key = os.environ.get("FUGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未設定 FUGLE_API_KEY 環境變數。請先申請富果 API 金鑰。"
        )

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=days)).isoformat()

    try:
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

    # 盤後才補今日 K 線；盤前跳過，避免帶入不完整的當日成交量
    if not premarket:
        df = _append_today_candle(symbol, df, api_key)
    return df


def _append_today_candle(symbol: str, df: pd.DataFrame, api_key: str) -> pd.DataFrame:
    """若歷史日 K 尾端非今日且即時報價已有今日成交，補上今日 K 線。"""
    import requests

    try:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
        resp = requests.get(url, headers={"X-API-KEY": api_key}, timeout=5)
        resp.raise_for_status()
        q = resp.json()

        today = date.today().isoformat()
        close_price = q.get("closePrice") or q.get("lastPrice")

        if q.get("date") != today or close_price is None:
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
            if isinstance(q.get("total"), dict) else 0,
        }
        return pd.concat([df, pd.DataFrame([today_row])], ignore_index=True)
    except Exception as e:
        print(f"[daily_data] {symbol} 補今日 K 線失敗（忽略）：{e}")
        return df
