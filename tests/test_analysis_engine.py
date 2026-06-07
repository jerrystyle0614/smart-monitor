"""test_analysis_engine.py — AnalysisEngine 測試"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")

from bot.analysis.engine import AnalysisEngine
from bot.analysis.cache import AnalysisCache


@pytest.fixture
def engine():
    """建立測試用 AnalysisEngine（禁用快取）"""
    return AnalysisEngine(use_cache=False)


@pytest.fixture
def cache():
    """建立測試用快取"""
    return AnalysisCache(cache_dir="cache/analysis_test")


class TestAnalysisCache:
    """快取測試"""

    def test_cache_set_and_get(self, cache):
        """測試快取的設定和讀取"""
        stock_id = "2330"
        analysis_type = "pre_market"
        result = {"technical": "test", "value": 123}

        cache.set(stock_id, analysis_type, result)
        cached = cache.get(stock_id, analysis_type)

        assert cached is not None
        assert cached["technical"] == "test"
        assert cached["value"] == 123

    def test_cache_key_generation(self, cache):
        """測試快取鍵生成"""
        key = cache._get_cache_key("2330", "pre_market")
        assert key == "2330_pre_market"


class TestAnalysisEngine:
    """AnalysisEngine 測試"""

    def test_engine_initialization(self, engine):
        """引擎初始化"""
        assert engine.client is not None
        assert engine.model == "claude-3-5-sonnet-20241022"

    @patch("bot.analysis.engine.Anthropic")
    def test_analyze_pre_market_with_mock(self, mock_anthropic, engine):
        """盤前分析（Mock Claude API）"""
        # 模擬 Claude API 回應
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"trend": "上升", "support": 120, "summary": "測試"}'
            )
        ]
        engine.client.messages.create = MagicMock(return_value=mock_response)

        result = engine.analyze_pre_market(
            stock_id="2330",
            stock_name="台積電",
            candle_data="[...K線資料...]",
            current_price=125.0,
        )

        assert "technical" in result
        assert "entry_exit" in result
        assert "risks" in result
        assert "timestamp" in result
