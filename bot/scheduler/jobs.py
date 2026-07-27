"""
jobs.py — 排程任務實現
選股推薦的任務邏輯。

注意：盤前/盤後分析已統一由 MonitorEngine 負責（背景監控引擎），
不在此排程，以避免重複推播。
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from bot.user_store import UserStore
from bot.line.client import LineClient
from bot.stock_picker.engine import StockPickerEngine
from bot.data.market_trend import fetch_market_data, analyze_market_trend, build_market_trend_message


logger = logging.getLogger(__name__)


class ScheduledJobs:
    """排程任務集合"""

    def __init__(
        self,
        user_store=None,
        line_client=None,
        stock_picker_engine=None,
        tg_client=None,
    ):
        # type: (Optional[UserStore], Optional[LineClient], Optional[StockPickerEngine], Optional[Any]) -> None
        self.user_store = user_store or UserStore()
        self.line_client = line_client or LineClient()
        self.stock_picker_engine = stock_picker_engine
        self.tg_client = tg_client

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

    def prescan_daily(self) -> None:
        """每日盤後預掃（13:40）— 建立選股候選清單"""
        try:
            from bot.services.prescan import run_prescan
            count = run_prescan()
            logger.info(f"[prescan] 完成，候選股 {count} 支")
        except Exception as e:
            logger.error(f"[prescan] 預掃失敗：{e}")

    def market_trend_daily(self):
        # type: () -> None
        """
        每日大盤走勢推播（08:50）
        抓取美股昨收資料，Claude 分析後推播給所有有效使用者。
        """
        if datetime.now().weekday() >= 5:  # 週六、日不推播
            logger.info("[market_trend] 週末，跳過推播")
            return

        try:
            market_data = fetch_market_data()
            if not market_data:
                logger.warning("[market_trend] 市場資料取得失敗，跳過推播")
                return

            ai_analysis = analyze_market_trend(market_data)
            fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            message = build_market_trend_message(ai_analysis, fetched_at)

            # LINE 使用者
            line_store = UserStore(platform="line")
            for uid in line_store.get_all_active_users():
                try:
                    self.line_client.push(uid, message)
                except Exception as e:
                    logger.error("[market_trend] LINE 推播失敗 uid={}: {}".format(uid, e))

            # Telegram 使用者
            if self.tg_client:
                tg_store = UserStore(platform="telegram")
                for uid in tg_store.get_all_active_users():
                    try:
                        self.tg_client.push(uid, message)
                    except Exception as e:
                        logger.error("[market_trend] TG 推播失敗 uid={}: {}".format(uid, e))

        except Exception as e:
            logger.error("[market_trend] 排程執行失敗：{}".format(e))

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
