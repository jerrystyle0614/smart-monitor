"""
jobs.py — 排程任務實現
包含盤前分析、盤後分析、選股推薦的任務邏輯
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from bot.analysis.engine import AnalysisEngine
from bot.user_store import UserStore
from bot.line_client import LineClient
from bot.stock_picker.engine import StockPickerEngine


logger = logging.getLogger(__name__)


class ScheduledJobs:
    """排程任務集合"""

    def __init__(
        self,
        user_store: Optional[UserStore] = None,
        line_client: Optional[LineClient] = None,
        analysis_engine: Optional[AnalysisEngine] = None,
        stock_picker_engine: Optional[StockPickerEngine] = None,
    ):
        self.user_store = user_store or UserStore()
        self.line_client = line_client or LineClient()
        self.analysis_engine = analysis_engine or AnalysisEngine(use_cache=False)
        self.stock_picker_engine = stock_picker_engine

    def pre_market_analysis(self) -> Dict[str, Any]:
        """
        每日盤前分析（08:30）
        對所有用戶的監控清單執行分析並推播
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "users_processed": 0,
            "stocks_analyzed": 0,
            "errors": [],
        }

        try:
            # 取得所有有監控股票的用戶
            monitoring_users = self.user_store.get_all_monitoring_users()
            result["users_processed"] = len(monitoring_users)

            for uid in monitoring_users:
                try:
                    watchlist = self.user_store.get_watchlist(uid)
                    if not watchlist:
                        continue

                    # 對每支監控股票執行分析
                    analyses = []
                    for stock in watchlist:
                        stock_id = stock.get("stock_id", "")
                        stock_name = stock.get("stock_name", "")

                        try:
                            analysis = self.analysis_engine.analyze_pre_market(
                                stock_id=stock_id,
                                stock_name=stock_name,
                                candle_data="[...]",  # 待從 Fugle 取得
                                current_price=0.0,    # 待從 Fugle 取得
                            )
                            if analysis:
                                analyses.append({
                                    "stock_id": stock_id,
                                    "stock_name": stock_name,
                                    "analysis": analysis,
                                })
                                result["stocks_analyzed"] += 1
                        except Exception as e:
                            logger.error(f"[pre_market] {stock_id} 分析失敗: {e}")
                            result["errors"].append(f"{stock_id}: {str(e)}")

                    # 如果有分析結果，推播給用戶
                    if analyses:
                        self._push_pre_market_results(uid, analyses)

                except Exception as e:
                    logger.error(f"[pre_market] 用戶 {uid} 處理失敗: {e}")
                    result["errors"].append(f"User {uid}: {str(e)}")

        except Exception as e:
            logger.error(f"[pre_market] 批量分析失敗: {e}")
            result["errors"].append(f"Batch process failed: {str(e)}")

        return result

    def post_market_analysis(self) -> Dict[str, Any]:
        """
        每日盤後分析（13:35）
        對所有用戶的監控清單執行分析並推播
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "users_processed": 0,
            "stocks_analyzed": 0,
            "errors": [],
        }

        try:
            monitoring_users = self.user_store.get_all_monitoring_users()
            result["users_processed"] = len(monitoring_users)

            for uid in monitoring_users:
                try:
                    watchlist = self.user_store.get_watchlist(uid)
                    if not watchlist:
                        continue

                    analyses = []
                    for stock in watchlist:
                        stock_id = stock.get("stock_id", "")
                        stock_name = stock.get("stock_name", "")

                        try:
                            analysis = self.analysis_engine.analyze_post_market(
                                stock_id=stock_id,
                                stock_name=stock_name,
                                candle_data="[...]",
                                current_price=0.0,
                            )
                            if analysis:
                                analyses.append({
                                    "stock_id": stock_id,
                                    "stock_name": stock_name,
                                    "analysis": analysis,
                                })
                                result["stocks_analyzed"] += 1
                        except Exception as e:
                            logger.error(f"[post_market] {stock_id} 分析失敗: {e}")
                            result["errors"].append(f"{stock_id}: {str(e)}")

                    if analyses:
                        self._push_post_market_results(uid, analyses)

                except Exception as e:
                    logger.error(f"[post_market] 用戶 {uid} 處理失敗: {e}")
                    result["errors"].append(f"User {uid}: {str(e)}")

        except Exception as e:
            logger.error(f"[post_market] 批量分析失敗: {e}")
            result["errors"].append(f"Batch process failed: {str(e)}")

        return result

    def _push_pre_market_results(self, uid: str, analyses: List[Dict]) -> None:
        """推播盤前分析結果"""
        try:
            # 格式化訊息
            message = self._format_pre_market_message(analyses)
            if message:
                self.line_client.push(uid, message)
        except Exception as e:
            logger.error(f"[push] 盤前推播失敗: {e}")

    def _push_post_market_results(self, uid: str, analyses: List[Dict]) -> None:
        """推播盤後分析結果"""
        try:
            message = self._format_post_market_message(analyses)
            if message:
                self.line_client.push(uid, message)
        except Exception as e:
            logger.error(f"[push] 盤後推播失敗: {e}")

    def _format_pre_market_message(self, analyses: List[Dict]) -> Optional[str]:
        """格式化盤前訊息"""
        if not analyses:
            return None

        lines = ["📊 盤前分析\n"]
        for item in analyses:
            stock_id = item.get("stock_id", "")
            stock_name = item.get("stock_name", "")
            analysis = item.get("analysis", {})

            trend = analysis.get("technical", {}).get("trend", "N/A")
            lines.append(f"\n{stock_name}({stock_id}): {trend}")

        return "".join(lines)

    def _format_post_market_message(self, analyses: List[Dict]) -> Optional[str]:
        """格式化盤後訊息"""
        if not analyses:
            return None

        lines = ["📊 盤後分析\n"]
        for item in analyses:
            stock_id = item.get("stock_id", "")
            stock_name = item.get("stock_name", "")
            analysis = item.get("analysis", {})

            trend = analysis.get("technical", {}).get("trend", "N/A")
            lines.append(f"\n{stock_name}({stock_id}): {trend}")

        return "".join(lines)

    def stock_picker_daily(self) -> Dict[str, Any]:
        """
        每日選股掃描（08:00）
        執行 StockPickerEngine 並將結果推播給所有用戶
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "stocks_found": 0,
            "users_notified": 0,
            "errors": [],
        }

        if not self.stock_picker_engine:
            logger.warning("[stock_picker] StockPickerEngine 未初始化")
            return result

        try:
            # 執行選股掃描
            recommended_stocks = self.stock_picker_engine.scan()
            result["stocks_found"] = len(recommended_stocks)

            if not recommended_stocks:
                logger.info("[stock_picker] 未發現符合條件的股票")
                return result

            # 推播給所有用戶
            all_users = self.user_store.get_all_monitoring_users()
            for uid in all_users:
                try:
                    message = self._format_stock_picker_message(recommended_stocks)
                    if message:
                        self.line_client.push(uid, message)
                        result["users_notified"] += 1
                except Exception as e:
                    logger.error(f"[stock_picker] 用戶 {uid} 推播失敗: {e}")
                    result["errors"].append(f"User {uid}: {str(e)}")

        except Exception as e:
            logger.error(f"[stock_picker] 掃描失敗: {e}")
            result["errors"].append(f"Scan failed: {str(e)}")

        return result

    def _format_stock_picker_message(self, stocks: List) -> Optional[str]:
        """格式化選股推薦訊息"""
        if not stocks:
            return None

        lines = ["🎯 今日選股推薦\n"]
        for stock in stocks:
            stock_id = getattr(stock, "stock_id", "")
            stock_name = getattr(stock, "stock_name", "")
            lines.append(f"\n• {stock_name}({stock_id})")

        lines.append("\n\n💡 輸入『1』可將股票加入監控清單")
        return "".join(lines)
