"""
pre_market.py — 盤前分析服務
單步問答：選股票 → 立即執行分析並推播
"""

from typing import Tuple, Any, Optional

from bot.services.base import Step, ScriptedService
from bot.data.fugle_client import FugleClient
from bot.analysis.engine import AnalysisEngine
from bot.analysis_runner import run_analysis_for_user, AnalysisMode


def push_to_line(uid, message, line):
    # type: (str, str, Any) -> None
    """LINE push 封裝（可被測試 patch 覆蓋）"""
    line.push(uid, message)


class PreMarketService(ScriptedService):
    """盤前分析服務"""

    def __init__(self):
        self.name = "pre_market"
        self.steps = [
            Step(
                field="stock_id",
                question="請問要分析哪支股票？（輸入名稱或代號）",
                validate=self._validate_stock,
                optional=False,
            ),
        ]
        self.analysis_engine = AnalysisEngine(use_cache=True)
        self.fugle_client = FugleClient()

    def _validate_stock(self, text):
        # type: (str) -> Tuple[bool, Any, str]
        """驗證股票"""
        client = FugleClient()
        result = client.verify_stock(text)
        if not result:
            return False, None, "找不到此股票，請重新輸入"
        return True, result, ""

    def on_complete(self, uid, draft, store, line, reply_token=""):
        # type: (str, dict, Any, Any, str) -> None
        """執行分析並推播"""
        stock_info = draft.get("stock_id", {})
        stock_id = stock_info.get("stock_id") if isinstance(stock_info, dict) else stock_info
        stock_name = stock_info.get("stock_name", "") if isinstance(stock_info, dict) else ""

        line.reply(reply_token, "⏳ 正在進行盤前分析，請稍候...")

        try:
            # 獲取最近 20 日 K 線資料
            candle_data = self._fetch_candle_data(stock_id)

            if candle_data:
                # 從 K 線資料中提取昨日收盤價（倒數第二筆，因為今日盤前還沒有今日K線）
                df = self.fugle_client.fetch_candles(stock_id, days=20)
                current_price = 0.0
                if df is not None and len(df) > 0:
                    # 盤前時使用昨日收盤價
                    current_price = float(df.iloc[-1].get("close", 0))

                # 呼叫 AnalysisEngine 進行分析
                analysis_result = self.analysis_engine.analyze_pre_market(
                    stock_id=stock_id,
                    stock_name=stock_name,
                    candle_data=candle_data,
                    current_price=current_price,
                )

                if analysis_result:
                    # 格式化訊息並推播
                    message = self._format_analysis_message(
                        stock_id, stock_name, current_price, analysis_result
                    )
                    push_to_line(uid, message, line)
                else:
                    # 分析失敗，回退到舊流程
                    self._fallback_analysis(uid, stock_id, stock_name, line)
            else:
                # K 線資料不可用，回退
                self._fallback_analysis(uid, stock_id, stock_name, line)

        except Exception as e:
            print(f"[pre_market] 分析失敗：{e}")
            self._fallback_analysis(uid, stock_id, stock_name, line)

        # 分析完後設定風險評估狀態，等待使用者主動輸入持股數
        store.set_service_state(uid, "risk_assessment", None, {
            "stock_id": stock_id,
            "stock_name": stock_name,
            "analysis_mode": "pre_market",
            "_step": "ask_shares",
        }, None)
        line.push(uid,
            "💰 想做更精確的風險評估嗎？\n\n"
            "請輸入你目前持有幾股？\n"
            "例如：1000\n\n"
            "（輸入『跳過』略過風險評估）"
        )

    def _fetch_candle_data(self, stock_id: str) -> Optional[str]:
        """
        取得最近 20 日 K 線資料並格式化為字串。
        回傳格式化的 K 線資料字串，或 None（失敗）
        """
        try:
            df = self.fugle_client.fetch_candles(stock_id, days=20)
            if df is None or len(df) == 0:
                return None

            # 格式化 DataFrame 為易讀的字串
            lines = ["日期\t\t開盤\t\t高\t\t低\t\t收盤\t\t成交量"]
            for _, row in df.iterrows():
                date_str = str(row.get("date", ""))[:10]
                open_price = row.get("open", 0)
                high_price = row.get("high", 0)
                low_price = row.get("low", 0)
                close_price = row.get("close", 0)
                volume = int(row.get("volume", 0))
                lines.append(
                    f"{date_str}\t{open_price:.2f}\t{high_price:.2f}\t"
                    f"{low_price:.2f}\t{close_price:.2f}\t{volume:,}"
                )
            return "\n".join(lines)
        except Exception as e:
            print(f"[pre_market] 取得 K 線資料失敗：{e}")
            return None

    def _format_analysis_message(
        self, stock_id: str, stock_name: str, current_price: float, analysis: dict
    ) -> str:
        """
        將分析結果格式化為易讀的 LINE 訊息。
        回傳格式化的訊息字串。
        """
        msg_parts = [f"📊 盤前分析 - {stock_name} ({stock_id})"]
        msg_parts.append(f"目前價格：{current_price:.2f} 元")
        msg_parts.append("")

        # 技術面分析
        technical = analysis.get("technical", {})
        if technical:
            msg_parts.append("🔍 技術面")
            if isinstance(technical, dict):
                msg_parts.append(f"- 趨勢：{technical.get('trend', '未知')}")
                support = technical.get("support")
                if support:
                    msg_parts.append(f"- 支撐：{support}")
                resistance = technical.get("resistance")
                if resistance:
                    msg_parts.append(f"- 壓力：{resistance}")
                pattern = technical.get("pattern")
                if pattern:
                    msg_parts.append(f"- 形態：{pattern}")
                summary = technical.get("summary")
                if summary:
                    msg_parts.append(f"- 總結：{summary}")
            else:
                msg_parts.append(f"- {technical}")
            msg_parts.append("")

        # 進出場建議
        entry_exit = analysis.get("entry_exit", {})
        if entry_exit:
            msg_parts.append("💡 進出場建議")
            if isinstance(entry_exit, dict):
                entry_price = entry_exit.get("entry_price")
                if entry_price:
                    msg_parts.append(f"- 進場價：{entry_price}")
                stop_loss = entry_exit.get("stop_loss")
                if stop_loss:
                    msg_parts.append(f"- 停損：{stop_loss}")
                targets = entry_exit.get("exit_targets")
                if targets:
                    if isinstance(targets, dict):
                        msg_parts.append(
                            f"- 目標：短期 {targets.get('short_term')} / "
                            f"中期 {targets.get('medium_term')}"
                        )
                    else:
                        msg_parts.append(f"- 目標：{targets}")
                risk_level = entry_exit.get("risk_level")
                if risk_level:
                    msg_parts.append(f"- 風險等級：{risk_level}")
                suitable = entry_exit.get("suitable_today")
                if suitable is not None:
                    msg_parts.append(
                        f"- 今日適合操作：{'✅ 是' if suitable else '❌ 否'}"
                    )
            msg_parts.append("")

        # 風險提示
        risks = analysis.get("risks", {})
        if risks:
            msg_parts.append("⚠️ 風險提示")
            if isinstance(risks, dict):
                tech_risks = risks.get("technical_risks", [])
                if tech_risks:
                    for risk in tech_risks:
                        msg_parts.append(f"- 技術風險：{risk}")
                op_risks = risks.get("operation_risks", [])
                if op_risks:
                    for risk in op_risks:
                        msg_parts.append(f"- 操作風險：{risk}")
                market_risks = risks.get("market_risks", [])
                if market_risks:
                    for risk in market_risks:
                        msg_parts.append(f"- 市場風險：{risk}")
                caution = risks.get("overall_caution_level")
                if caution:
                    msg_parts.append(f"- 整體警示等級：{caution}")
            msg_parts.append("")

        msg_parts.append("⚠️ 本分析僅供參考，投資決策應自負其責")

        return "\n".join(msg_parts)

    def _fallback_analysis(self, uid: str, stock_id: str, stock_name: str, line):
        # type: (str, str, str, Any) -> None
        """
        分析失敗時，回退到舊的 run_analysis_for_user 流程。
        確保服務在 AnalysisEngine 異常時仍能正常運作。
        """
        try:
            result = run_analysis_for_user(
                {"stock_id": stock_id, "stock_name": stock_name, "cost_price": None},
                {},
                AnalysisMode.PREMARKET,
            )

            if result:
                push_to_line(uid, result["title"], line)
                push_to_line(uid, result["message"], line)
            else:
                push_to_line(uid, f"無法取得 {stock_name} ({stock_id}) 的分析結果", line)
        except Exception as e:
            print(f"[pre_market] 回退分析也失敗：{e}")
            push_to_line(uid, f"分析服務暫時不可用，請稍後再試", line)
