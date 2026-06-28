"""tests/test_market_trend.py"""
from unittest.mock import patch, MagicMock
import pytest


def _make_hist(prices):
    """建立假的 yfinance history DataFrame"""
    import pandas as pd
    return pd.DataFrame({"Close": prices}, index=pd.date_range("2026-06-27", periods=len(prices)))


class TestFetchMarketData:
    def test_returns_dict_with_required_keys(self):
        """fetch_market_data 應回傳含 sp500/nasdaq/sox 的 dict"""
        from bot.data.market_trend import fetch_market_data

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_hist([100.0, 102.0])

        with patch("bot.data.market_trend.yf.Ticker", return_value=mock_ticker):
            result = fetch_market_data()

        assert result is not None
        assert "sp500" in result
        assert "change_pct" in result["sp500"]

    def test_returns_none_when_all_fail(self):
        """所有 symbol 都失敗時回傳 None"""
        from bot.data.market_trend import fetch_market_data

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("network error")

        with patch("bot.data.market_trend.yf.Ticker", return_value=mock_ticker):
            result = fetch_market_data()

        assert result is None

    def test_partial_failure_still_returns_data(self):
        """部分 symbol 失敗時，成功的部分仍回傳"""
        from bot.data.market_trend import fetch_market_data

        success_ticker = MagicMock()
        success_ticker.history.return_value = _make_hist([100.0, 102.0])

        fail_ticker = MagicMock()
        fail_ticker.history.side_effect = Exception("fail")

        # 交替成功/失敗
        tickers = [success_ticker, fail_ticker, success_ticker, fail_ticker, success_ticker, fail_ticker]
        ticker_iter = iter(tickers)

        with patch("bot.data.market_trend.yf.Ticker", side_effect=lambda _: next(ticker_iter)):
            result = fetch_market_data()

        assert result is not None

    def test_returns_none_when_hist_empty(self):
        """history 回傳空 DataFrame 時該 symbol 跳過"""
        from bot.data.market_trend import fetch_market_data
        import pandas as pd

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()  # 空 DataFrame

        with patch("bot.data.market_trend.yf.Ticker", return_value=mock_ticker):
            result = fetch_market_data()

        assert result is None


class TestAnalyzeMarketTrend:
    def test_returns_string(self):
        """analyze_market_trend 應回傳非空字串"""
        from bot.data.market_trend import analyze_market_trend

        sample_data = {
            "sp500": {"price": 5500.0, "change_pct": 0.5},
            "nasdaq": {"price": 17500.0, "change_pct": 0.8},
            "sox": {"price": 4800.0, "change_pct": 1.2},
            "tsm_adr": {"price": 185.0, "change_pct": 0.3},
            "vix": {"price": 16.5, "change_pct": -2.0},
            "usd_twd": {"price": 32.5, "change_pct": 0.1},
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="✅ 今日大盤偏多，適合操作")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("bot.data.market_trend.Anthropic", return_value=mock_client):
            result = analyze_market_trend(sample_data)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_fallback_on_api_error(self):
        """Claude API 失敗時回傳格式化的純數據摘要（不拋例外）"""
        from bot.data.market_trend import analyze_market_trend

        sample_data = {
            "sp500": {"price": 5500.0, "change_pct": 0.5},
        }

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        with patch("bot.data.market_trend.Anthropic", return_value=mock_client):
            result = analyze_market_trend(sample_data)

        assert isinstance(result, str)
        assert len(result) > 0


class TestBuildMarketTrendMessage:
    def test_includes_header_and_disclaimer(self):
        """build_market_trend_message 應含標題和免責聲明"""
        from bot.data.market_trend import build_market_trend_message

        result = build_market_trend_message("今日偏多", "2026-06-29 08:50")
        assert "大盤走勢" in result
        assert "僅供參考" in result

    def test_includes_ai_analysis(self):
        """build_market_trend_message 應含 AI 分析內容"""
        from bot.data.market_trend import build_market_trend_message

        result = build_market_trend_message("今日偏多，適合操作", "2026-06-29 08:50")
        assert "今日偏多" in result
