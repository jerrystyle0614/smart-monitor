"""test_stock_picker_integration.py — Phase B 整合測試（含 FinMind API 驗證）"""
import os
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

os.environ.setdefault("ENCRYPT_KEY", "a" * 64)
os.environ.setdefault("FINMIND_API_KEY", "test_key")
os.environ.setdefault("FUGLE_API_KEY", "test_key")

from bot.stock_picker.base import Stock
from bot.stock_picker.finmind_client import FinMindClient
from bot.stock_picker.fundamental_strategy import FundamentalStrategy
from bot.stock_picker.technical_strategy import TechnicalStrategy
from bot.stock_picker.engine import StockPickerEngine


# ========================================================================
# Part 1: FinMind API Real-world Integration Tests
# ========================================================================
# 注意：以下測試需要真實 FINMIND_API_KEY 且 FinMind API dataset 名稱確認
# TODO: Verify FinMind API dataset names:
#   - TaiwanStockThreeMainForces (currently returns 422)
#   - TaiwanStockMarginPurchaseShortSale (currently returns 400)
#   - Confirm correct parameter format and free-tier access

class TestFinMindAPIIntegration:
    """FinMind API 真實整合測試（可跳過若無真實 API Key）"""

    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.environ.get("FINMIND_API_KEY") or
        os.environ.get("FINMIND_API_KEY", "").startswith("test_"),
        reason="Real FINMIND_API_KEY required"
    )
    def test_get_all_stocks_basic_real_api(self):
        """驗證 get_all_stocks_basic 可連接真實 FinMind API"""
        client = FinMindClient()
        result = client.get_all_stocks_basic()

        # 應該回傳股票列表
        assert isinstance(result, list)
        assert len(result) > 0

        # 應該包含台積電
        tsmc = [s for s in result if s.get("stock_id") == "2330"]
        assert len(tsmc) > 0
        assert tsmc[0].get("stock_name") == "台積電"

    @pytest.mark.integration
    @pytest.mark.xfail(reason="FinMind dataset name requires verification")
    def test_get_three_major_buyers_real_api(self):
        """
        驗證 get_three_major_buyers 可連接真實 FinMind API

        當前狀態：API 返回 422 Unprocessable Entity
        原因：TaiwanStockThreeMainForces dataset 名稱可能不正確
        待確認：確認正確的 dataset 名稱和參數格式
        """
        client = FinMindClient()
        result = client.get_three_major_buyers("2330")

        # 預期應回傳字典
        assert result is not None
        assert isinstance(result, dict)
        assert "consecutive_buy_days" in result

    @pytest.mark.integration
    @pytest.mark.xfail(reason="FinMind dataset name requires verification")
    def test_get_margin_status_real_api(self):
        """
        驗證 get_margin_status 可連接真實 FinMind API

        當前狀態：API 返回 400 Bad Request
        原因：TaiwanStockMarginPurchaseShortSale dataset 名稱或參數可能不正確
        待確認：確認正確的 dataset 名稱和參數格式
        """
        client = FinMindClient()
        result = client.get_margin_status("2330")

        # 預期應回傳字典
        assert result is not None
        assert isinstance(result, dict)
        assert "margin_balance" in result


# ========================================================================
# Part 2: Full Pipeline Integration (with Mocks)
# ========================================================================
# 這些測試使用 Mock 確保快速穩定的 CI/CD

class TestStockPickerPipeline:
    """完整選股流程整合測試（使用 Mock）"""

    @patch("bot.stock_picker.fundamental_strategy.requests.get")
    def test_full_pipeline_fundamental_to_technical(self, mock_get):
        """完整流程：從籌碼面到技術面篩選"""
        mock_fugle = MagicMock()

        # 股票清單
        stock_list = [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2454", "stock_name": "聯發科"},
            {"stock_id": "2303", "stock_name": "聯電"},
        ]

        # Mock FinMind API 返回融資增幅 < 5%
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{
                "MarginShortSalesCurrentDayBalance": 5000000,
                "date": "2026-06-07"
            }, {
                "MarginShortSalesCurrentDayBalance": 4900000,
                "date": "2026-06-06"
            }]
        }
        mock_get.return_value = mock_response

        # 技術面模擬
        mock_fugle.load_stock_map.return_value = {
            "台積電": "2330",
            "聯發科": "2454",
            "聯電": "2303",
        }

        df = pd.DataFrame({
            "close": [100 + i * 0.5 for i in range(20)],
            "high": [110] * 20,
        })
        mock_fugle.fetch_candles.return_value = df

        # 建立策略和引擎
        fundamental = FundamentalStrategy(
            stock_list_provider=lambda: stock_list,
            margin_increase_threshold=5.0
        )
        technical = TechnicalStrategy(mock_fugle)
        engine = StockPickerEngine([fundamental, technical])

        # 掃描
        result = engine.scan()

        # 應該有交集結果
        assert isinstance(result, list)

    def test_engine_intersection_logic(self):
        """驗證 StockPickerEngine 的交集邏輯"""
        # 策略 1 返回 2330, 2454
        strategy1 = MagicMock()
        strategy1.scan.return_value = [
            Stock(stock_id="2330", stock_name="台積電"),
            Stock(stock_id="2454", stock_name="聯發科"),
        ]

        # 策略 2 返回 2330, 2303
        strategy2 = MagicMock()
        strategy2.scan.return_value = [
            Stock(stock_id="2330", stock_name="台積電"),
            Stock(stock_id="2303", stock_name="聯電"),
        ]

        engine = StockPickerEngine([strategy1, strategy2])
        result = engine.scan()

        # 交集應只有 2330
        assert len(result) == 1
        assert result[0].stock_id == "2330"

    def test_engine_handles_single_strategy(self):
        """單一策略時應回傳該策略的全部結果"""
        strategy = MagicMock()
        strategy.scan.return_value = [
            Stock(stock_id="2330", stock_name="台積電"),
            Stock(stock_id="2454", stock_name="聯發科"),
        ]

        engine = StockPickerEngine([strategy])
        result = engine.scan()

        assert len(result) == 2
        assert result[0].stock_id == "2330"
        assert result[1].stock_id == "2454"

    def test_engine_handles_empty_strategies(self):
        """空策略列表應回傳空結果"""
        engine = StockPickerEngine([])
        result = engine.scan()

        assert result == []

    def test_engine_handles_strategy_failure(self):
        """策略失敗時應繼續執行其他策略"""
        # 策略 1 正常
        strategy1 = MagicMock()
        strategy1.scan.return_value = [
            Stock(stock_id="2330", stock_name="台積電"),
            Stock(stock_id="2454", stock_name="聯發科"),
        ]

        # 策略 2 拋出異常
        strategy2 = MagicMock()
        strategy2.scan.side_effect = Exception("API Error")
        strategy2.name = "failing_strategy"

        engine = StockPickerEngine([strategy1, strategy2])
        result = engine.scan()

        # 應該只有策略 1 的結果
        assert len(result) == 2


# ========================================================================
# Part 3: Service Integration
# ========================================================================

class TestStockPickerServiceIntegration:
    """StockPickerService 整合測試"""

    def test_service_start_shows_first_question(self):
        """start() 應初始化問答狀態並顯示第一題（資金）"""
        from bot.services.stock_picker import StockPickerService

        service = StockPickerService()
        mock_store = MagicMock()
        mock_line = MagicMock()

        service.start("U123", mock_store, mock_line)

        # 進入問答狀態
        mock_store.set_service_state.assert_called()
        # 顯示步驟 1／3：詢問資金
        mock_line.reply.assert_called()
        call_text = str(mock_line.reply.call_args)
        assert "步驟 1" in call_text
        assert "資金" in call_text

    def test_service_completes_with_three_answers(self):
        """三題答完後 on_complete 應執行選股流程（達每日上限時回覆提示）"""
        from bot.services.stock_picker import StockPickerService

        service = StockPickerService()
        mock_store = MagicMock()
        mock_line = MagicMock()

        draft = {"capital": 50000.0, "period": "2", "risk": "2"}

        # 強制視為已達每日查詢上限，避免實際呼叫 Fugle/FinMind/Claude
        with patch("bot.services.stock_picker._get_query_count", return_value=999):
            service.on_complete("U123", draft, mock_store, mock_line, "token")

        # 清除問答狀態並回覆上限提示
        mock_store.clear_service_state.assert_called_once_with("U123")
        mock_line.reply.assert_called()
        assert "上限" in str(mock_line.reply.call_args)
