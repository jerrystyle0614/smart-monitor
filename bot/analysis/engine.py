"""
engine.py — Claude AI 分析引擎
"""

import os
import json
from typing import Optional, Dict, Any
from datetime import datetime

from anthropic import Anthropic

from bot.analysis.cache import AnalysisCache
from bot.analysis.prompts import (
    TECHNICAL_ANALYSIS_PROMPT,
    TECHNICAL_ANALYSIS_PRE_MARKET_PROMPT,
    ENTRY_EXIT_PROMPT,
    RISK_ALERT_PROMPT,
)


class AnalysisEngine:
    """Claude AI 深度分析引擎"""

    def __init__(self, use_cache: bool = True):
        self.client = Anthropic()
        self.model = "claude-sonnet-4-5"
        self.cache = AnalysisCache() if use_cache else None

    def analyze_pre_market(
        self,
        stock_id: str,
        stock_name: str,
        candle_data: str,
        current_price: float,
        market_context_text: str = "",
    ) -> Dict[str, Any]:
        """
        盤前分析：技術面 + 進出場建議 + 風險提示
        market_context_text: 格式化後的市場背景文字（可選）
        回傳 {
            "technical": {...},
            "entry_exit": {...},
            "risks": {...},
            "timestamp": "ISO8601"
        }
        """
        # 檢查快取
        if self.cache:
            cached = self.cache.get(stock_id, "pre_market")
            if cached:
                return cached

        # 技術面分析（盤前版本含市場背景）
        technical = self._analyze_technical(
            stock_id, stock_name, candle_data, market_context_text=market_context_text
        )
        if not technical:
            return {}

        # 進出場建議
        entry_exit = self._analyze_entry_exit(
            stock_id, stock_name, current_price, technical, "盤前"
        )
        if not entry_exit:
            entry_exit = {}

        # 風險提示
        risks = self._analyze_risks(technical, entry_exit)
        if not risks:
            risks = {}

        result = {
            "technical": technical,
            "entry_exit": entry_exit,
            "risks": risks,
            "timestamp": datetime.now().isoformat(),
        }

        # 保存快取
        if self.cache:
            self.cache.set(stock_id, "pre_market", result)

        return result

    def analyze_post_market(
        self,
        stock_id: str,
        stock_name: str,
        candle_data: str,
        current_price: float,
    ) -> Dict[str, Any]:
        """
        盤後分析：技術面 + 進出場建議（明日展望）+ 風險提示
        """
        # 檢查快取
        if self.cache:
            cached = self.cache.get(stock_id, "post_market")
            if cached:
                return cached

        # 技術面分析
        technical = self._analyze_technical(
            stock_id, stock_name, candle_data
        )
        if not technical:
            return {}

        # 進出場建議（轉為明日展望）
        entry_exit = self._analyze_entry_exit(
            stock_id, stock_name, current_price, technical, "盤後"
        )
        if not entry_exit:
            entry_exit = {}

        # 風險提示
        risks = self._analyze_risks(technical, entry_exit)
        if not risks:
            risks = {}

        result = {
            "technical": technical,
            "entry_exit": entry_exit,
            "risks": risks,
            "timestamp": datetime.now().isoformat(),
        }

        # 保存快取
        if self.cache:
            self.cache.set(stock_id, "post_market", result)

        return result

    def _analyze_technical(
        self,
        stock_id: str,
        stock_name: str,
        candle_data: str,
        market_context_text: str = "",
    ) -> Optional[Dict[str, Any]]:
        """技術面分析（有 market_context_text 時使用盤前含市場背景 prompt）"""
        if market_context_text:
            prompt = TECHNICAL_ANALYSIS_PRE_MARKET_PROMPT.format(
                stock_id=stock_id,
                stock_name=stock_name,
                candle_data=candle_data,
                market_context=market_context_text,
            )
        else:
            prompt = TECHNICAL_ANALYSIS_PROMPT.format(
                stock_id=stock_id,
                stock_name=stock_name,
                candle_data=candle_data,
            )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # 嘗試解析 JSON
            try:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_str = response_text[start:end]
                    return json.loads(json_str)
            except Exception:
                # 若無法解析，直接回傳文字
                return {"summary": response_text}

        except Exception as e:
            print(f"[analysis] 技術面分析失敗：{e}")
            return None

    def _analyze_entry_exit(
        self,
        stock_id: str,
        stock_name: str,
        current_price: float,
        technical: Dict[str, Any],
        analysis_time: str,
    ) -> Optional[Dict[str, Any]]:
        """進出場建議"""
        prompt = ENTRY_EXIT_PROMPT.format(
            stock_id=stock_id,
            stock_name=stock_name,
            current_price=current_price,
            technical_analysis=json.dumps(technical, ensure_ascii=False),
            analysis_time=analysis_time,
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            try:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_str = response_text[start:end]
                    return json.loads(json_str)
            except Exception:
                return {"suggestion": response_text}

        except Exception as e:
            print(f"[analysis] 進出場分析失敗：{e}")
            return None

    def _analyze_risks(
        self,
        technical: Dict[str, Any],
        entry_exit: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """風險提示"""
        prompt = RISK_ALERT_PROMPT.format(
            stock_name="股票",
            stock_id="XXXX",
            technical_analysis=json.dumps(technical, ensure_ascii=False),
            entry_exit_analysis=json.dumps(entry_exit, ensure_ascii=False),
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            try:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_str = response_text[start:end]
                    return json.loads(json_str)
            except Exception:
                return {"warnings": response_text}

        except Exception as e:
            print(f"[analysis] 風險提示失敗：{e}")
            return None
