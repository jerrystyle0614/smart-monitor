"""
technical_strategy.py — 技術面篩選策略
篩選條件：收盤價 > MA20 + 回撤 < 8% + 過去 5 日有上漲
"""

from typing import List

import pandas as pd

from bot.stock_picker.base import Stock, Strategy


class TechnicalStrategy(Strategy):
    """技術面策略"""
    
    def __init__(
        self,
        fugle_client,
        ma_period: int = 20,
        pullback_threshold: float = 8.0,
    ):
        self.name = "technical"
        self.client = fugle_client
        self.ma_period = ma_period
        self.pullback_threshold = pullback_threshold
    
    def scan(self) -> List[Stock]:
        """
        掃描符合技術面條件的股票。
        條件：
        1. 收盤價 > MA20（趨勢向上）
        2. 距離 20 日高點回撤 < threshold %（未過度下跌）
        3. 過去 5 日有上漲（動能未衰）
        """
        try:
            stock_map = self.client.load_stock_map()
        except Exception as e:
            print(f"[technical] 無法載入股票清單：{e}")
            return []
        
        qualified = []
        
        for stock_name, stock_id in stock_map.items():
            try:
                df = self.client.fetch_candles(stock_id, days=60)
                if df is None or len(df) < self.ma_period:
                    continue
                
                # 計算 MA20
                df["close"] = pd.to_numeric(df["close"], errors="coerce")
                df["high"] = pd.to_numeric(df["high"], errors="coerce")
                
                ma20 = df["close"].tail(self.ma_period).mean()
                current_close = df["close"].iloc[-1]
                high20 = df["high"].tail(self.ma_period).max()
                
                # 條件 1：收盤價 > MA20
                if current_close <= ma20:
                    continue
                
                # 條件 2：回撤 < threshold %
                if high20 > 0:
                    pullback_pct = (high20 - current_close) / high20 * 100
                    if pullback_pct >= self.pullback_threshold:
                        continue
                
                # 條件 3：過去 5 日有上漲
                recent_closes = df["close"].tail(5).values
                if len(recent_closes) < 5:
                    continue
                
                has_gain = any(recent_closes[i] < recent_closes[i + 1] for i in range(4))
                if not has_gain:
                    continue
                
                # 通過所有條件
                qualified.append(Stock(stock_id=stock_id, stock_name=stock_name))
            
            except Exception as e:
                print(f"[technical] {stock_id} 分析失敗：{e}")
                continue
        
        return qualified
