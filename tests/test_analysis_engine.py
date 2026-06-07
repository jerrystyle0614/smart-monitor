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


class TestPreMarketIntegration:
    """PreMarketService 整合測試"""

    def test_pre_market_service_integration(self):
        """測試 PreMarketService 整合 AnalysisEngine"""
        from bot.services.pre_market import PreMarketService

        service = PreMarketService()

        # 驗證服務已初始化分析引擎
        assert service.analysis_engine is not None
        assert service.fugle_client is not None

    def test_pre_market_on_complete_with_analysis(self):
        """測試 on_complete 呼叫分析引擎"""
        import pandas as pd
        from bot.services.pre_market import PreMarketService

        service = PreMarketService()
        mock_store = MagicMock()
        mock_line = MagicMock()

        draft = {
            "stock_id": {
                "stock_id": "2330",
                "stock_name": "台積電"
            }
        }

        # Mock FugleClient 和 AnalysisEngine
        with patch.object(service, "fugle_client") as mock_fugle:
            with patch.object(service, "analysis_engine") as mock_analysis:
                # 模擬股價
                mock_fugle.get_quote.return_value = {
                    "close_price": 920.0,
                    "stock_id": "2330"
                }

                # 模擬 K 線資料（返回 DataFrame）
                df = pd.DataFrame({
                    "date": ["2026-06-01", "2026-06-02", "2026-06-03"],
                    "open": [910.0, 915.0, 920.0],
                    "high": [915.0, 920.0, 925.0],
                    "low": [905.0, 910.0, 915.0],
                    "close": [912.0, 918.0, 920.0],
                    "volume": [10000000, 12000000, 11000000]
                })
                mock_fugle.fetch_candles.return_value = df

                # 模擬分析結果
                mock_analysis.analyze_pre_market.return_value = {
                    "technical": {
                        "trend": "上升",
                        "support": 910.0,
                        "resistance": 930.0,
                        "pattern": "上升趨勢",
                        "summary": "技術面好轉"
                    },
                    "entry_exit": {
                        "entry_price": 920.0,
                        "stop_loss": 910.0,
                        "exit_targets": {"short_term": 925.0, "medium_term": 935.0},
                        "risk_level": "中",
                        "suitable_today": True
                    },
                    "risks": {
                        "technical_risks": ["可能反轉"],
                        "operation_risks": ["資金控管"],
                        "market_risks": [],
                        "overall_caution_level": "低"
                    },
                    "timestamp": "2026-06-07T08:30:00"
                }

                service.on_complete("U123", draft, mock_store, mock_line)

                # 驗證分析引擎被呼叫
                mock_analysis.analyze_pre_market.assert_called_once()
                # 驗證推播被呼叫
                assert mock_line.push.called or mock_line.reply.called
                # 驗證清除狀態
                mock_store.clear_service_state.assert_called_once_with("U123")

    def test_format_analysis_message(self):
        """測試訊息格式化"""
        from bot.services.pre_market import PreMarketService

        service = PreMarketService()

        analysis_result = {
            "technical": {
                "trend": "上升",
                "support": 910.0,
                "resistance": 930.0,
                "pattern": "雙底",
                "summary": "技術面好轉"
            },
            "entry_exit": {
                "entry_price": 920.0,
                "stop_loss": 910.0,
                "exit_targets": {"short_term": 925.0, "medium_term": 935.0},
                "risk_level": "中",
                "suitable_today": True
            },
            "risks": {
                "technical_risks": ["可能反轉"],
                "operation_risks": [],
                "market_risks": ["流動性不足"],
                "overall_caution_level": "低"
            }
        }

        message = service._format_analysis_message(
            "2330", "台積電", 920.0, analysis_result
        )

        # 驗證訊息包含關鍵元素
        assert "盤前分析" in message
        assert "台積電" in message
        assert "2330" in message
        assert "目前價格" in message
        assert "技術面" in message
        assert "進出場建議" in message
        assert "風險提示" in message
        assert "上升" in message  # trend
        assert "920.0" in message or "920" in message  # entry_price

    def test_on_complete_fallback_on_error(self):
        """測試分析失敗時的回退機制"""
        from bot.services.pre_market import PreMarketService

        service = PreMarketService()
        mock_store = MagicMock()
        mock_line = MagicMock()

        draft = {
            "stock_id": {
                "stock_id": "2330",
                "stock_name": "台積電"
            }
        }

        # Mock FugleClient 回傳 None（失敗）
        with patch.object(service, "fugle_client") as mock_fugle:
            mock_fugle.get_quote.return_value = None

            with patch("bot.services.pre_market.run_analysis_for_user") as mock_fallback:
                mock_fallback.return_value = {
                    "title": "📊 盤前分析",
                    "message": "分析結果..."
                }

                service.on_complete("U123", draft, mock_store, mock_line)

                # 驗證回退被呼叫
                mock_fallback.assert_called_once()
                # 驗證清除狀態
                mock_store.clear_service_state.assert_called_once_with("U123")


class TestPostMarketIntegration:
    """PostMarketService 整合測試"""

    def test_post_market_service_integration(self):
        """測試 PostMarketService 整合 AnalysisEngine"""
        from bot.services.post_market import PostMarketService

        service = PostMarketService()

        # 驗證服務已初始化分析引擎
        assert service.analysis_engine is not None
        assert service.fugle_client is not None

    def test_post_market_on_complete_with_analysis(self):
        """測試 on_complete 呼叫分析引擎"""
        import pandas as pd
        from bot.services.post_market import PostMarketService

        service = PostMarketService()
        mock_store = MagicMock()
        mock_line = MagicMock()

        draft = {
            "stock_id": {
                "stock_id": "2330",
                "stock_name": "台積電"
            }
        }

        # Mock FugleClient 和 AnalysisEngine
        with patch.object(service, "fugle_client") as mock_fugle:
            with patch.object(service, "analysis_engine") as mock_analysis:
                # 模擬股價
                mock_fugle.get_quote.return_value = {
                    "close_price": 920.0,
                    "stock_id": "2330"
                }

                # 模擬 K 線資料（返回 DataFrame）
                df = pd.DataFrame({
                    "date": ["2026-06-01", "2026-06-02", "2026-06-03"],
                    "open": [910.0, 915.0, 920.0],
                    "high": [915.0, 920.0, 925.0],
                    "low": [905.0, 910.0, 915.0],
                    "close": [912.0, 918.0, 920.0],
                    "volume": [10000000, 12000000, 11000000]
                })
                mock_fugle.fetch_candles.return_value = df

                # 模擬分析結果（盤後版本）
                mock_analysis.analyze_post_market.return_value = {
                    "technical": {
                        "trend": "盤整",
                        "support": 910.0,
                        "resistance": 930.0,
                        "pattern": "上升趨勢",
                        "summary": "收盤表現穩定"
                    },
                    "entry_exit": {
                        "entry_price": 920.0,
                        "stop_loss": 910.0,
                        "exit_targets": {"short_term": 925.0, "medium_term": 935.0},
                        "risk_level": "中",
                        "suitable_today": False  # 盤後不適合當日操作
                    },
                    "risks": {
                        "technical_risks": ["近期高點風險"],
                        "operation_risks": ["盤後操作風險"],
                        "market_risks": [],
                        "overall_caution_level": "中"
                    },
                    "timestamp": "2026-06-07T13:35:00"
                }

                service.on_complete("U123", draft, mock_store, mock_line)

                # 驗證分析引擎被呼叫
                mock_analysis.analyze_post_market.assert_called_once()
                # 驗證推播被呼叫
                assert mock_line.push.called or mock_line.reply.called
                # 驗證清除狀態
                mock_store.clear_service_state.assert_called_once_with("U123")

    def test_format_analysis_message_post_market(self):
        """測試訊息格式化（盤後版本）"""
        from bot.services.post_market import PostMarketService

        service = PostMarketService()

        analysis_result = {
            "technical": {
                "trend": "盤整",
                "support": 910.0,
                "resistance": 930.0,
                "pattern": "盤整區間",
                "summary": "收盤表現穩定"
            },
            "entry_exit": {
                "entry_price": 920.0,
                "stop_loss": 910.0,
                "exit_targets": {"short_term": 925.0, "medium_term": 935.0},
                "risk_level": "中",
                "suitable_today": False
            },
            "risks": {
                "technical_risks": ["可能突破"],
                "operation_risks": [],
                "market_risks": ["流動性不足"],
                "overall_caution_level": "中"
            }
        }

        message = service._format_analysis_message(
            "2330", "台積電", 920.0, analysis_result
        )

        # 驗證訊息包含關鍵元素（盤後版本特定文字）
        assert "盤後分析" in message
        assert "台積電" in message
        assert "2330" in message
        assert "今日收盤價" in message  # 區別於盤前的「目前價格」
        assert "技術面回顧" in message  # 區別於盤前的「技術面」
        assert "明日展望" in message  # 區別於盤前的「進出場建議」
        assert "建議監控價" in message  # 區別於盤前的「進場價」
        assert "建議監控點" in message  # 區別於盤前的「停損」
        assert "風險警示" in message  # 區別於盤前的「風險提示」
        assert "盤整" in message  # trend
        assert "920.0" in message or "920" in message  # entry_price

    def test_post_market_on_complete_fallback_on_error(self):
        """測試盤後分析失敗時的回退機制"""
        from bot.services.post_market import PostMarketService

        service = PostMarketService()
        mock_store = MagicMock()
        mock_line = MagicMock()

        draft = {
            "stock_id": {
                "stock_id": "2330",
                "stock_name": "台積電"
            }
        }

        # Mock FugleClient 回傳 None（失敗）
        with patch.object(service, "fugle_client") as mock_fugle:
            mock_fugle.get_quote.return_value = None

            with patch("bot.services.post_market.run_analysis_for_user") as mock_fallback:
                mock_fallback.return_value = {
                    "title": "📊 盤後分析",
                    "message": "分析結果..."
                }

                service.on_complete("U123", draft, mock_store, mock_line)

                # 驗證回退被呼叫
                mock_fallback.assert_called_once()
                # 驗證清除狀態
                mock_store.clear_service_state.assert_called_once_with("U123")
