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
                # 驗證進入風險評估狀態
                mock_store.set_service_state.assert_called()

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
                # 驗證進入風險評估狀態
                mock_store.set_service_state.assert_called()


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
                # 驗證進入風險評估狀態
                mock_store.set_service_state.assert_called()

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
                # 驗證進入風險評估狀態
                mock_store.set_service_state.assert_called()


class TestE2EPipeline:
    """端對端完整流程測試"""

    def test_full_pipeline_pre_market_e2e(self):
        """盤前分析 E2E 測試：問答 → 分析 → 推播"""
        import pandas as pd
        from bot.services.pre_market import PreMarketService

        service = PreMarketService()
        mock_store = MagicMock()
        mock_line = MagicMock()

        # 模擬使用者選擇股票「2330」的完整流程
        draft = {
            "stock_id": {
                "stock_id": "2330",
                "stock_name": "台積電"
            }
        }

        with patch.object(service, "fugle_client") as mock_fugle:
            with patch.object(service, "analysis_engine") as mock_analysis:
                # Step 1: 模擬股價查詢
                mock_fugle.get_quote.return_value = {
                    "close_price": 920.0,
                    "stock_id": "2330"
                }

                # Step 2: 模擬 K 線資料
                df = pd.DataFrame({
                    "date": ["2026-06-01", "2026-06-02", "2026-06-03"],
                    "open": [910.0, 915.0, 920.0],
                    "high": [915.0, 920.0, 925.0],
                    "low": [905.0, 910.0, 915.0],
                    "close": [912.0, 918.0, 920.0],
                    "volume": [10000000, 12000000, 11000000]
                })
                mock_fugle.fetch_candles.return_value = df

                # Step 3: 模擬 Claude 分析結果
                expected_analysis = {
                    "technical": {
                        "trend": "上升",
                        "support": 910.0,
                        "resistance": 930.0,
                        "pattern": "雙底",
                        "summary": "技術面好轉，價格突破上升趨勢線"
                    },
                    "entry_exit": {
                        "entry_price": 920.0,
                        "stop_loss": 910.0,
                        "exit_targets": {"short_term": 925.0, "medium_term": 935.0},
                        "risk_level": "低",
                        "suitable_today": True
                    },
                    "risks": {
                        "technical_risks": ["可能高檔回撤"],
                        "operation_risks": ["資金控管"],
                        "market_risks": [],
                        "overall_caution_level": "低"
                    },
                    "timestamp": "2026-06-07T08:30:00"
                }
                mock_analysis.analyze_pre_market.return_value = expected_analysis

                # Step 4: 執行完整流程
                service.on_complete("U123", draft, mock_store, mock_line)

                # Step 5: 驗證整個管道
                # 驗證 Fugle API 被呼叫（取 K 線資料 + 取昨收價，共兩次）
                mock_fugle.fetch_candles.assert_called()

                # 驗證分析引擎被正確呼叫
                mock_analysis.analyze_pre_market.assert_called_once()
                call_args = mock_analysis.analyze_pre_market.call_args
                assert call_args[1]["stock_id"] == "2330"
                assert call_args[1]["stock_name"] == "台積電"
                assert call_args[1]["current_price"] == 920.0

                # 驗證推播被呼叫（第一則為分析訊息，第二則為風險評估提問）
                assert mock_line.push.called
                pushed_message = mock_line.push.call_args_list[0][0][1]
                assert "盤前分析" in pushed_message
                assert "台積電" in pushed_message
                assert "2330" in pushed_message
                assert "上升" in pushed_message  # trend
                assert "920" in pushed_message  # entry_price

                # 驗證進入風險評估狀態
                mock_store.set_service_state.assert_called()

    def test_full_pipeline_post_market_e2e(self):
        """盤後分析 E2E 測試：問答 → 分析 → 推播"""
        import pandas as pd
        from bot.services.post_market import PostMarketService

        service = PostMarketService()
        mock_store = MagicMock()
        mock_line = MagicMock()

        # 模擬使用者選擇股票「2330」的完整流程
        draft = {
            "stock_id": {
                "stock_id": "2330",
                "stock_name": "台積電"
            }
        }

        with patch.object(service, "fugle_client") as mock_fugle:
            with patch.object(service, "analysis_engine") as mock_analysis:
                # Step 1: 模擬股價查詢
                mock_fugle.get_quote.return_value = {
                    "close_price": 922.0,
                    "stock_id": "2330"
                }

                # Step 2: 模擬 K 線資料
                df = pd.DataFrame({
                    "date": ["2026-06-01", "2026-06-02", "2026-06-03"],
                    "open": [910.0, 915.0, 920.0],
                    "high": [915.0, 920.0, 925.0],
                    "low": [905.0, 910.0, 915.0],
                    "close": [912.0, 918.0, 922.0],
                    "volume": [10000000, 12000000, 11000000]
                })
                mock_fugle.fetch_candles.return_value = df

                # Step 3: 模擬 Claude 盤後分析結果
                expected_analysis = {
                    "technical": {
                        "trend": "盤整",
                        "support": 910.0,
                        "resistance": 930.0,
                        "pattern": "收斂楔形",
                        "summary": "收盤表現穩定，等待突破信號"
                    },
                    "entry_exit": {
                        "entry_price": 925.0,
                        "stop_loss": 910.0,
                        "exit_targets": {"short_term": 935.0, "medium_term": 950.0},
                        "risk_level": "中",
                        "suitable_today": False
                    },
                    "risks": {
                        "technical_risks": ["近期高點風險"],
                        "operation_risks": ["盤後操作風險"],
                        "market_risks": [],
                        "overall_caution_level": "中"
                    },
                    "timestamp": "2026-06-07T13:35:00"
                }
                mock_analysis.analyze_post_market.return_value = expected_analysis

                # Step 4: 執行完整流程
                service.on_complete("U123", draft, mock_store, mock_line)

                # Step 5: 驗證整個管道
                # 驗證 Fugle API 被呼叫（取 K 線資料 + 取昨收價，共兩次）
                mock_fugle.fetch_candles.assert_called()

                # 驗證分析引擎被正確呼叫
                mock_analysis.analyze_post_market.assert_called_once()
                call_args = mock_analysis.analyze_post_market.call_args
                assert call_args[1]["stock_id"] == "2330"
                assert call_args[1]["stock_name"] == "台積電"
                assert call_args[1]["current_price"] == 922.0

                # 驗證推播被呼叫（第一則為分析訊息，第二則為風險評估提問）
                assert mock_line.push.called
                pushed_message = mock_line.push.call_args_list[0][0][1]
                assert "盤後分析" in pushed_message
                assert "台積電" in pushed_message
                assert "2330" in pushed_message
                assert "盤整" in pushed_message  # trend
                assert "922" in pushed_message  # current_price

                # 驗證進入風險評估狀態
                mock_store.set_service_state.assert_called()


class TestCacheValidation:
    """快取機制驗證測試"""

    def test_cache_reduces_api_calls(self):
        """驗證快取減少 API 呼叫：第一次呼叫 → 第二次使用快取"""
        import shutil

        # 準備測試資料
        stock_id = "2330_test"  # 使用唯一標識以避免現有快取
        stock_name = "台積電"
        candle_data = "日期\t開盤\t高\t低\t收盤\n2026-06-07\t920\t925\t915\t920"
        current_price = 920.0

        # 使用獨立的快取目錄
        cache_dir = "cache/analysis_test_api_calls"

        with patch("bot.analysis.engine.Anthropic") as mock_anthropic_class:
            # Mock Anthropic 客戶端
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client

            # Mock Claude API 回應
            mock_response = MagicMock()
            mock_response.content = [
                MagicMock(
                    text='{"trend": "上升", "support": 910, "summary": "技術面好轉"}'
                )
            ]
            mock_client.messages.create.return_value = mock_response

            # 建立引擎，使用獨立快取目錄
            engine = AnalysisEngine(use_cache=True)
            engine.cache.cache_dir = __import__("pathlib").Path(cache_dir)
            engine.cache.cache_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: 第一次呼叫 → 呼叫 Claude API
            result1 = engine.analyze_pre_market(
                stock_id=stock_id,
                stock_name=stock_name,
                candle_data=candle_data,
                current_price=current_price,
            )

            api_call_count_after_first = mock_client.messages.create.call_count
            assert api_call_count_after_first >= 3, f"第一次呼叫應該調用 3 次 Claude API，但只有 {api_call_count_after_first} 次"

            # Step 2: 第二次呼叫 → 返回快取結果（不呼叫 API）
            result2 = engine.analyze_pre_market(
                stock_id=stock_id,
                stock_name=stock_name,
                candle_data=candle_data,
                current_price=current_price,
            )

            api_call_count_after_second = mock_client.messages.create.call_count
            # 快取機制應確保不增加新的 API 呼叫
            assert (
                api_call_count_after_second == api_call_count_after_first
            ), f"快取應該防止重複 API 呼叫（期望 {api_call_count_after_first}，實際 {api_call_count_after_second}）"

            # Step 3: 驗證兩次結果一致
            assert result1.get("technical") == result2.get("technical")

        # 清理測試快取目錄
        if __import__("pathlib").Path(cache_dir).exists():
            shutil.rmtree(cache_dir)

    def test_cache_expires_after_ttl(self):
        """驗證快取在 TTL 過期後重新呼叫 API"""
        cache = AnalysisCache(cache_dir="cache/analysis_test_ttl")

        stock_id = "2330"
        analysis_type = "pre_market"
        original_result = {"trend": "上升", "support": 910}

        # 設定短 TTL 以便測試
        cache.ttl = 2  # 2 秒

        # Step 1: 設定快取
        cache.set(stock_id, analysis_type, original_result)

        # Step 2: 立即讀取 → 應該返回快取
        cached_result = cache.get(stock_id, analysis_type)
        assert cached_result is not None
        assert cached_result == original_result

        # Step 3: 等待快取過期
        import time
        time.sleep(3)

        # Step 4: 讀取已過期快取 → 應該返回 None
        expired_result = cache.get(stock_id, analysis_type)
        assert expired_result is None, "過期快取應該被清除"

        # 清理
        import shutil
        cache_path = cache.cache_dir
        if cache_path.exists():
            shutil.rmtree(cache_path)

    def test_different_stocks_use_different_cache(self):
        """驗證不同股票使用不同的快取"""
        cache = AnalysisCache(cache_dir="cache/analysis_test_different")

        stock1_result = {"trend": "上升", "support": 910}
        stock2_result = {"trend": "下降", "support": 900}

        # 設定兩支股票的快取
        cache.set("2330", "pre_market", stock1_result)
        cache.set("2454", "pre_market", stock2_result)

        # 驗證獨立快取
        assert cache.get("2330", "pre_market") == stock1_result
        assert cache.get("2454", "pre_market") == stock2_result

        # 清理
        import shutil
        cache_path = cache.cache_dir
        if cache_path.exists():
            shutil.rmtree(cache_path)


class TestErrorHandling:
    """錯誤處理與降級機制測試"""

    def test_graceful_degradation_on_api_failure(self):
        """測試 API 失敗時的優雅降級：服務不崩潰，提供回退訊息"""
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

        with patch.object(service, "fugle_client") as mock_fugle:
            with patch.object(service, "analysis_engine") as mock_analysis:
                # Mock AnalysisEngine 拋出異常
                mock_analysis.analyze_pre_market.side_effect = Exception(
                    "Claude API 暫時無法連線"
                )

                # Mock FugleClient 返回成功（但分析失敗）
                mock_fugle.get_quote.return_value = {"close_price": 920.0}
                import pandas as pd
                df = pd.DataFrame({
                    "date": ["2026-06-07"],
                    "open": [920.0],
                    "high": [925.0],
                    "low": [915.0],
                    "close": [920.0],
                    "volume": [10000000]
                })
                mock_fugle.fetch_candles.return_value = df

                # Mock 回退函式
                with patch("bot.services.pre_market.run_analysis_for_user") as mock_fallback:
                    mock_fallback.return_value = {
                        "title": "📊 盤前分析",
                        "message": "暫時無法進行深度分析，使用簡易報價"
                    }

                    # 執行應該不會崩潰
                    service.on_complete("U123", draft, mock_store, mock_line)

                    # 驗證：服務不崩潰，回退被呼叫
                    mock_fallback.assert_called_once()

                    # 驗證進入風險評估狀態
                    mock_store.set_service_state.assert_called()

    def test_graceful_degradation_on_data_fetch_failure(self):
        """測試資料獲取失敗時的優雅降級"""
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

        with patch.object(service, "fugle_client") as mock_fugle:
            # Mock FugleClient 回傳 None（資料不可用）
            mock_fugle.get_quote.return_value = None
            mock_fugle.fetch_candles.return_value = None

            # Mock 回退函式
            with patch("bot.services.pre_market.run_analysis_for_user") as mock_fallback:
                mock_fallback.return_value = {
                    "title": "📊 盤前分析",
                    "message": "無法取得股票資料"
                }

                # 執行應該不會崩潰
                service.on_complete("U123", draft, mock_store, mock_line)

                # 驗證回退被呼叫
                mock_fallback.assert_called_once()

                # 驗證進入風險評估狀態
                mock_store.set_service_state.assert_called()

    def test_engine_handles_malformed_api_response(self):
        """測試引擎處理格式不正確的 API 回應（優雅降級）"""
        engine = AnalysisEngine(use_cache=False)

        with patch.object(engine.client.messages, "create") as mock_api:
            # Mock 返回無效 JSON 的回應，但仍包含純文字摘要
            mock_response = MagicMock()
            mock_response.content = [
                MagicMock(text="This is not JSON, just plain text response with summary: 技術面穩定")
            ]
            mock_api.return_value = mock_response

            # 應該優雅地降級，而不是崩潰
            result = engine.analyze_pre_market(
                stock_id="2330",
                stock_name="台積電",
                candle_data="[...]",
                current_price=920.0,
            )

            # 當技術面分析失敗時，analyze_pre_market 返回空字典（已被 service 層的回退機制處理）
            # 驗證：應該返回某種結果字典，不拋異常
            assert isinstance(result, dict)
            # 當 _analyze_technical 失敗（返回 None），整個 analyze_pre_market 返回 {}
            # 這由 service 層的 _fallback_analysis 處理
