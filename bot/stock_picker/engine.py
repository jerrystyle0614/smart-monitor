"""
engine.py — StockPickerEngine 掃描引擎
組合多個策略結果，取交集
"""

from typing import List

from bot.stock_picker.base import Stock, Strategy


class StockPickerEngine:
    """選股掃描引擎"""
    
    def __init__(self, strategies: List[Strategy]):
        self.strategies = strategies
    
    def scan(self) -> List[Stock]:
        """
        執行所有策略並取交集。
        回傳同時符合所有策略條件的股票列表。
        """
        if not self.strategies:
            return []
        
        # 執行第一個策略
        results = [set(self.strategies[0].scan())]
        
        # 執行其餘策略
        for strategy in self.strategies[1:]:
            try:
                strategy_result = set(strategy.scan())
                results.append(strategy_result)
            except Exception as e:
                print(f"[engine] {strategy.name} 執行失敗：{e}")
                continue
        
        if not results:
            return []
        
        # 取交集
        intersection = results[0]
        for i in range(1, len(results)):
            intersection &= results[i]
        
        return sorted(list(intersection), key=lambda s: s.stock_id)
