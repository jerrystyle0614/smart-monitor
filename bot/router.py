"""
router.py — ServiceRouter 主路由模組
路由使用者訊息到對應的服務或選單
"""

from typing import Optional, Dict, List

from bot.services.stock_monitor import StockMonitorService
from bot.services.pre_market import PreMarketService
from bot.services.post_market import PostMarketService
from bot.services.stock_picker import StockPickerService
from bot.services.etf_picker import ETFPickerService


SERVICE_PERMISSIONS = {
    "stock_monitor": ["free", "basic", "pro"],
    "pre_market":    ["basic", "pro"],
    "post_market":   ["basic", "pro"],
    "stock_picker":  ["pro"],
    "etf_picker":    ["pro"],
}

_ADD_STOCK = StockMonitorService()
_PRE_MARKET = PreMarketService()
_POST_MARKET = PostMarketService()
_STOCK_PICKER = StockPickerService()
_ETF_PICKER = ETFPickerService()

_SERVICE_MAP = {
    "stock_monitor": _ADD_STOCK,
    "pre_market": _PRE_MARKET,
    "post_market": _POST_MARKET,
    "stock_picker": _STOCK_PICKER,
    "etf_picker": _ETF_PICKER,
}


class ServiceRouter:
    """主路由器，將 LINE 訊息分發到對應的服務"""

    def handle_message(self, uid, text, store, line, reply_token):
        # type: (str, str, object, object, str) -> None
        """處理訊息事件的 instance method 包裝"""
        handle_message(uid, text, store, line, reply_token)

    def handle_follow(self, uid, store, line):
        # type: (str, object, object) -> None
        """處理追蹤事件的 instance method 包裝"""
        handle_follow(uid, store, line)


def handle_follow(uid, store, line):
    # type: (str, object, object) -> None
    """處理追蹤事件。若用戶已初始化過（profile 存在），略過歡迎訊息避免重複推播。"""
    already_registered = store.get_plan(uid) != "free"
    store.set_plan(uid, "pro")

    # LINE 有時會重複送 follow event（重新連線、server 重啟等），用已初始化判斷排除
    if already_registered:
        return

    line.push(uid,
        "👋 歡迎使用 Smart 助理！\n\n"
        "我是您的投資助理。\n"
        "提供股票監控、盤前/盤後分析、選股推薦等服務。"
    )
    line.push(uid,
        "=================\n"
        "📊 Smart 助理\n\n"
        "請選擇服務：\n"
        "1️⃣ 股票監控\n"
        "2️⃣ 盤前分析\n"
        "3️⃣ 盤後分析\n"
        "4️⃣ 選股推薦\n"
        "5️⃣ ETF 推薦\n\n"
        "輸入數字選擇\n"
        "『狀態』— 查看監控清單\n"
        "『說明』或『說明 1~5』— 查看使用說明\n"
        "================="
    )


def handle_message(uid, text, store, line, reply_token):
    # type: (str, str, object, object, str) -> None
    """
    處理訊息。主路由邏輯：
    1. 冷卻檢查
    2. 確保用戶有 plan（若無則設為 pro）
    3. 問答進行中 → 交給服務處理
    4. stock_monitor_confirm 狀態 → 等待確認
    5. 其他 → 顯示選單或解析命令
    """
    text = text.strip()

    # 冷卻檢查
    if store.check_cooldown(uid):
        line.push(uid, "⏱️ 傳送訊息過於頻繁，請稍後再試。")
        return

    # 確保用戶有設置 plan（防止舊用戶被鎖定在 free 方案）
    if store.get_plan(uid) == "free":
        store.set_plan(uid, "pro")

    # 檢查問答是否進行中
    current_service = store.get_current_service(uid)

    # 等待股票監控確認
    if current_service == "stock_monitor_confirm":
        _handle_stock_confirm(uid, text, store, line, reply_token)
        return

    # 等待風險評估資金輸入
    if current_service == "risk_assessment":
        _handle_risk_assessment(uid, text, store, line, reply_token)
        return

    # 其他服務問答進行中
    if current_service is not None:
        _route_to_service(uid, text, current_service, store, line, reply_token)
        return

    # 主菜單路由
    if text in ("1", "2", "3", "4", "5"):
        _handle_menu(uid, text, store, line, reply_token)
    elif text in ("狀態", "status"):
        _show_watchlist(uid, store, line, reply_token)
    elif text.startswith("說明"):
        _handle_help(uid, text, line, reply_token)
    elif text.startswith("刪除 "):
        _handle_delete(uid, text, store, line, reply_token)
    else:
        _show_menu(uid, store, line, reply_token)


def _route_to_service(uid, text, service_name, store, line, reply_token):
    # type: (str, str, str, object, object, str) -> None
    """將訊息路由給活躍的服務"""
    service = _SERVICE_MAP.get(service_name)
    if not service:
        store.clear_service_state(uid)
        _show_menu(uid, store, line, reply_token)
        return

    result = service.handle_input(uid, text, store, line, reply_token)
    if result == "CANCEL":
        _show_menu(uid, store, line, reply_token)


def _handle_menu(uid, choice, store, line, reply_token):
    # type: (str, str, object, object, str) -> None
    """處理主菜單選擇 (1/2/3/4)"""
    plan = store.get_plan(uid)

    service_map = {
        "1": ("stock_monitor", _ADD_STOCK),
        "2": ("pre_market", _PRE_MARKET),
        "3": ("post_market", _POST_MARKET),
        "4": ("stock_picker", _STOCK_PICKER),
        "5": ("etf_picker", _ETF_PICKER),
    }

    service_name, service = service_map.get(choice, (None, None))
    if not service_name:
        _show_menu(uid, store, line, reply_token)
        return

    # 檢查權限
    allowed_plans = SERVICE_PERMISSIONS.get(service_name, [])
    if plan not in allowed_plans:
        if service_name in ("stock_picker", "etf_picker"):
            label = "選股推薦" if service_name == "stock_picker" else "ETF 推薦"
            line.reply(reply_token,
                f"⚠️ {label}為 pro 方案專屬功能。\n"
                "請聯絡管理員了解升級方式。"
            )
        else:
            line.reply(reply_token,
                "⚠️ 此功能需要升級方案才能使用。\n"
                "請聯絡管理員了解升級方式。"
            )
        return

    # 啟動服務
    service.start(uid, store, line, reply_token)


def _handle_stock_confirm(uid, text, store, line, reply_token):
    # type: (str, str, object, object, str) -> None
    """處理股票監控確認步驟（stock_monitor_confirm 狀態）"""
    if text == "取消":
        store.clear_service_state(uid)
        line.reply(reply_token, "已取消，輸入數字重新選擇服務。")
        _show_menu(uid, store, line, reply_token)
        return

    if text != "確認":
        line.reply(reply_token, "請輸入「確認」開始監控，或「取消」重新設定。")
        return

    draft = store.get_draft(uid)
    if not draft:
        store.clear_service_state(uid)
        _show_menu(uid, store, line, reply_token)
        return

    stock_info = draft.get("stock_id", {})
    if isinstance(stock_info, dict):
        stock_id = stock_info.get("stock_id", "")
        stock_name = stock_info.get("stock_name", "")
    else:
        stock_id = str(stock_info)
        stock_name = ""

    stop_loss = draft.get("stop_loss_moving")

    try:
        store.add_stock(uid, {
            "stock_id": stock_id,
            "stock_name": stock_name,
            "total_shares": str(draft.get("total_shares", 0)),
            "cost_price": str(draft.get("cost_price", 0)),
            "stop_loss_moving": str(stop_loss) if stop_loss is not None else None,
            "target_stage_1": None,
            "alerts_fired": {"stop": False, "target1": False},
        })
        line.reply(reply_token, "✅ 已開始監控 {}（{}）".format(stock_name, stock_id))
        _show_watchlist(uid, store, line, reply_token)
    except Exception as e:
        line.reply(reply_token, "❌ 無法保存監控設定：{}".format(e))

    store.clear_service_state(uid)


def _show_menu(uid, store, line, reply_token):
    # type: (str, object, object, str) -> None
    """顯示主菜單"""
    plan = store.get_plan(uid)

    menu = (
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 Smart 助理\n\n"
        "請選擇服務：\n"
        "1️⃣ 股票監控\n"
    )

    if plan in ("basic", "pro"):
        menu += "2️⃣ 盤前分析\n"
        menu += "3️⃣ 盤後分析\n"

    if plan == "pro":
        menu += "4️⃣ 選股推薦\n"
        menu += "5️⃣ ETF 推薦\n"

    menu += "\n輸入數字選擇服務\n"
    menu += "『狀態』— 查看監控清單\n"
    menu += "『說明』或『說明 1~5』— 查看使用說明\n"
    menu += "『取消』— 任何步驟中途回到此選單\n"
    menu += "━━━━━━━━━━━━━━━━━━"

    line.reply(reply_token, menu)


def _show_watchlist(uid, store, line, reply_token):
    # type: (str, object, object, str) -> None
    """顯示監控清單"""
    watchlist = store.get_watchlist(uid)

    if not watchlist:
        line.reply(reply_token, "📊 你還沒有監控任何股票。\n輸入『1』開始新增。")
        return

    msg = "📊 你的監控清單（{}/3）\n\n".format(len(watchlist))
    for i, stock in enumerate(watchlist, 1):
        stock_id = stock.get("stock_id", "")
        stock_name = stock.get("stock_name", "")
        shares = stock.get("total_shares")
        cost = stock.get("cost_price")
        stop_loss = stock.get("stop_loss_moving")

        msg += "{} {}（{}）\n".format(i, stock_name, stock_id)
        msg += "   持股 {} 股 | 均價 {} 元".format(shares, cost)
        if stop_loss:
            msg += " | 停損 {} 元".format(stop_loss)
        msg += "\n"

    # Telegram：附上刪除按鈕；LINE：顯示文字指令提示
    if hasattr(line, "_post"):
        from bot.telegram.keyboard import watchlist_delete_keyboard, to_inline_markup
        # chat_id 從 reply_token 解析：cbq:{qid}:{chat_id} 或 msg:{chat_id}:{msg_id}
        parts = reply_token.split(":")
        chat_id = parts[2] if parts[0] == "cbq" else parts[1]
        line.reply(reply_token, msg)
        line._post("sendMessage", {
            "chat_id": chat_id,
            "text": "點擊下方按鈕刪除監控：",
            "reply_markup": to_inline_markup(watchlist_delete_keyboard(watchlist)),
        })
    else:
        msg += "\n可用指令：\n"
        msg += "『1』— 新增監控\n"
        msg += "『刪除 [數字]』— 移除監控\n"
        msg += "『說明 1~4』— 查看各服務說明"
        line.reply(reply_token, msg)


def _handle_help(uid, text, line, reply_token):
    # type: (str, str, object, str) -> None
    """處理說明命令，支援『說明』或『說明 1』格式"""
    parts = text.split()

    # 主要說明
    main_help = (
        "📖 Smart 助理 使用說明\n\n"
        "📊 主要功能：\n"
        "1️⃣ 股票監控 — 輸入『說明 1』了解詳情\n"
        "2️⃣ 盤前分析 — 輸入『說明 2』了解詳情\n"
        "3️⃣ 盤後分析 — 輸入『說明 3』了解詳情\n"
        "4️⃣ 選股推薦 — 輸入『說明 4』了解詳情\n"
        "5️⃣ ETF 推薦 — 輸入『說明 5』了解詳情\n\n"
        "🛠️ 常用指令：\n"
        "『狀態』— 查看監控清單\n"
        "『刪除 [數字]』— 移除監控股票"
    )

    detail_helps = {
        "1": (
            "📖 股票監控詳細說明\n\n"
            "功能：自動監控股票價格，當達到停損或目標價時推播提醒。\n\n"
            "使用步驟：\n"
            "1. 輸入『1』開始新增監控\n"
            "2. 輸入股票名稱或代號\n"
            "3. 輸入持有股數\n"
            "4. 輸入買入均價\n"
            "5. 輸入停損價（可選，輸入『跳過』略過）\n"
            "6. 輸入『確認』完成設定\n\n"
            "提示：最多可同時監控 3 檔股票"
        ),
        "2": (
            "📖 盤前分析詳細說明\n\n"
            "功能：每日 08:30 自動推播股票技術面分析與進場建議。\n\n"
            "使用步驟：\n"
            "1. 輸入『2』選擇盤前分析\n"
            "2. 輸入要分析的股票名稱或代號\n"
            "3. 系統自動分析並推播結果\n\n"
            "分析內容：MA20 趨勢、支撐壓力、進場信號"
        ),
        "3": (
            "📖 盤後分析詳細說明\n\n"
            "功能：每日 13:35 自動推播股票技術面分析與出場建議。\n\n"
            "使用步驟：\n"
            "1. 輸入『3』選擇盤後分析\n"
            "2. 輸入要分析的股票名稱或代號\n"
            "3. 系統自動分析並推播結果\n\n"
            "分析內容：今日表現、獲利了結點位、風險提示"
        ),
        "4": (
            "📖 選股推薦詳細說明\n\n"
            "功能：每日掃描全市場，推薦籌碼面 + 技術面優質股票。\n\n"
            "使用步驟：\n"
            "1. 輸入『4』選擇選股推薦\n"
            "2. 輸入可用資金\n"
            "3. 選擇持有期間\n"
            "4. 選擇風險偏好\n\n"
            "篩選條件：主力進場、技術面突破、潛在獲利空間\n"
            "⚠️ 此功能為 pro 方案專屬"
        ),
        "5": (
            "📖 ETF 推薦詳細說明\n\n"
            "功能：依投資目標篩選適合的 ETF，AI 推薦 3 檔並說明操作策略。\n\n"
            "使用步驟：\n"
            "1. 輸入『5』選擇 ETF 推薦\n"
            "2. 輸入可用資金\n"
            "3. 選擇投資目標（大盤 / 高股息 / 主題）\n\n"
            "篩選條件：乖離率 < 8%、近30日不跌逾10%、高股息需殖利率 > 3%\n"
            "⚠️ 此功能為 pro 方案專屬"
        ),
    }

    # 檢查是否指定了服務編號
    if len(parts) == 2:
        service_num = parts[1]
        msg = detail_helps.get(service_num, main_help)
    else:
        msg = main_help

    line.reply(reply_token, msg)


def _handle_risk_assessment(uid, text, store, line, reply_token):
    # type: (str, str, object, object, str) -> None
    """處理風險評估兩步驟問答：ask_shares → ask_cost → 執行分析"""
    draft = store.get_draft(uid)
    step = draft.get("_step", "ask_shares")

    if text == "取消":
        store.clear_service_state(uid)
        line.reply(reply_token, "已取消，返回主選單。")
        _show_menu(uid, store, line, reply_token)
        return

    if text == "跳過":
        store.clear_service_state(uid)
        line.reply(reply_token, "已略過風險評估。")
        line.push_with_menu(uid, "分析結果已送出，需要其他服務嗎？")
        return

    # --- 第一步：等待持股數輸入 ---
    if step == "ask_shares":
        try:
            shares = int(text.replace(",", "").replace("，", ""))
            if shares <= 0:
                raise ValueError
        except ValueError:
            line.reply(reply_token,
                "❌ 請輸入正整數，例如：1000\n\n"
                "請輸入您目前 / 預計持有幾股？\n（輸入『跳過』略過）\n（輸入『取消』回主選單）"
            )
            return

        draft["shares"] = shares
        draft["_step"] = "ask_cost"
        store.set_service_state(uid, "risk_assessment", None, draft, None)
        line.reply(reply_token, "請輸入你的買入均價是多少元？\n例如：65\n\n（輸入『跳過』略過）\n（輸入『取消』回主選單）")
        return

    # --- 第二步：等待均價輸入 → 執行分析 ---
    if step == "ask_cost":
        try:
            cost_price = float(text.replace(",", "").replace("，", ""))
            if cost_price <= 0:
                raise ValueError
        except ValueError:
            line.reply(reply_token,
                "❌ 請輸入有效數字，例如：65\n\n"
                "請輸入你的買入均價是多少元？\n（輸入『跳過』略過）\n（輸入『取消』回主選單）"
            )
            return

        draft["cost_price"] = cost_price
        store.clear_service_state(uid)
        line.reply(reply_token, "⏳ 正在分析風險，請稍候...")
        _run_risk_analysis(uid, draft, line)
        return

    # 未知狀態，清除
    store.clear_service_state(uid)
    _show_menu(uid, store, line, reply_token)


def _run_risk_analysis(uid, draft, line):
    # type: (str, dict, object) -> None
    """執行 AI 風險評估並推播結果"""
    import os
    import anthropic
    from daily_data import fetch_candles
    from swing_strategy import analyze_swing

    stock_id = draft.get("stock_id", "")
    stock_name = draft.get("stock_name", "")
    shares = draft.get("shares", 0)
    cost_price = draft.get("cost_price", 0.0)
    analysis_mode = draft.get("analysis_mode", "post_market")

    try:
        df = fetch_candles(stock_id, days=60)
        result = analyze_swing(df, lookback=20, ma_days=20,
                               pullback_warn=5.0, pullback_alert=8.0, ma_warn=2.0)

        close = result.close
        ma20 = result.ma20
        high20 = result.high20

        # 損益計算
        capital = shares * cost_price
        current_value = shares * close
        unrealized_pnl = current_value - capital
        unrealized_pct = unrealized_pnl / capital * 100

        # 近20日 K 線（供 AI 判斷支撐壓力）
        kline_rows = df.tail(20)
        kline_lines = "日期\t開\t高\t低\t收\t量(張)\n"
        for _, row in kline_rows.iterrows():
            kline_lines += (
                f"{str(row.get('date',''))[:10]}\t"
                f"{row.get('open',0)}\t{row.get('high',0)}\t"
                f"{row.get('low',0)}\t{row.get('close',0)}\t"
                f"{int(row.get('volume',0)) // 1000:,}\n"
            )

        alert_lines = ""
        for a in result.alerts:
            alert_lines += f"- {a.title}：{a.message}\n"
        if not alert_lines:
            alert_lines = "- 無警示\n"

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            line.push(uid, "❌ 無法進行 AI 風險評估（API Key 未設定）")
            return

        # AI 判斷股票類型 → 選停損方式 → 計算停損/停利
        prompt = (
            f"你是台股風險管理顧問。請依照以下步驟為投資人建議停損和停利。\n\n"
            f"【股票】{stock_name}（{stock_id}）\n"
            f"【持股】{shares:,} 股，均價 {cost_price} 元\n"
            f"【投入成本】{capital:,.0f} 元\n"
            f"【目前收盤】{close} 元，市值 {current_value:,.0f} 元\n"
            f"【未實現損益】{unrealized_pnl:+,.0f} 元（{unrealized_pct:+.2f}%）\n"
            f"【MA20】{ma20:.2f} 元（股價偏離均線 {result.pct_from_ma20:+.2f}%）\n"
            f"【近20日最高收盤】{high20} 元（從高點回撤 {result.pullback_pct:.2f}%）\n"
            f"【系統訊號】\n{alert_lines}\n"
            f"【近20日 K 線】\n{kline_lines}\n\n"
            f"步驟一：判斷此股票類型（從以下選一）：\n"
            f"  - 大型權值股（市值大、法人持股高、波動穩定）\n"
            f"  - 中小型成長股（題材股、生技、AI 概念、波動大）\n"
            f"  - 高殖利率ETF（0056、00940、00878 等）\n"
            f"  - 景氣循環股（鋼鐵、航運、半導體設備）\n"
            f"  - 小型投機股（成交量小、波動極大）\n\n"
            f"步驟二：根據股票類型選擇最適合的停損方式：\n"
            f"  - ATR停損：適合大型權值股，依波動幅度設定\n"
            f"  - 技術面停損（MA20/前低）：適合一般波段股\n"
            f"  - 最大回撤停損：適合ETF、景氣循環股\n"
            f"  - 百分比停損：適合中小型成長股、投機股\n"
            f"  - 時間停損：適合題材股（可與其他方式並用）\n\n"
            f"步驟三：依選定方式計算今日建議停損價和停利目標。\n\n"
            f"回覆格式為 JSON，不要有其他文字：\n"
            f'{{"stock_type": "股票類型",'
            f'"stop_loss_method": "停損方式名稱",'
            f'"stop_loss_price": 數字,'
            f'"stop_loss_reason": "因為這是[股票類型]，採用[停損方式]，理由說明（1～2句）",'
            f'"tp1_price": 數字, "tp1_reason": "第一停利理由（1句）",'
            f'"tp2_price": 數字, "tp2_reason": "第二停利理由（1句）",'
            f'"risk_level": "低/中/高",'
            f'"summary": "白話風險評估（5～7句）"}}'
        )

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )

        # 解析 AI 回傳的 JSON
        import json as _json
        raw = response.content[0].text.strip()
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            ai_data = _json.loads(raw[start:end])
        except Exception:
            ai_data = {}

        stock_type = ai_data.get("stock_type", "")
        stop_loss_method = ai_data.get("stop_loss_method", "")
        stop_loss_price = float(ai_data.get("stop_loss_price", round(close * 0.95, 1)))
        stop_loss_reason = ai_data.get("stop_loss_reason", "AI 建議停損點")
        tp1_price = float(ai_data.get("tp1_price", round(high20, 1)))
        tp1_reason = ai_data.get("tp1_reason", "第一停利目標")
        tp2_price = float(ai_data.get("tp2_price", round(high20 * 1.08, 1)))
        tp2_reason = ai_data.get("tp2_reason", "第二停利目標")
        risk_level = ai_data.get("risk_level", "中")
        summary = ai_data.get("summary", raw)

        # 根據 AI 停損/停利計算損益金額
        loss_at_stop = shares * (close - stop_loss_price)
        loss_pct_at_stop = (close - stop_loss_price) / close * 100
        gain_at_tp1 = shares * (tp1_price - close)
        gain_pct_tp1 = (tp1_price - close) / close * 100
        gain_at_tp2 = shares * (tp2_price - close)
        gain_pct_tp2 = (tp2_price - close) / close * 100
        risk_amt = abs(loss_at_stop)
        reward_amt = abs(gain_at_tp1)
        rr_ratio = round(reward_amt / risk_amt, 1) if risk_amt > 0 else 0

        pnl_sign = "+" if unrealized_pnl >= 0 else ""
        msg = (
            f"📊 風險評估｜{stock_name}（{stock_id}）\n\n"
            f"持股：{shares:,} 股｜均價：{cost_price} 元\n"
            f"成本：{capital:,.0f} 元｜市值：{current_value:,.0f} 元\n"
            f"損益：{pnl_sign}{unrealized_pnl:,.0f} 元（{pnl_sign}{unrealized_pct:.2f}%）\n\n"
            f"📌 股票類型：{stock_type}\n"
            f"📐 停損方式：{stop_loss_method}\n\n"
            f"🛡️ 停損：{stop_loss_price} 元\n"
            f"   理由：{stop_loss_reason}\n"
            f"   若觸及：損失約 {loss_at_stop:,.0f} 元（{loss_pct_at_stop:.1f}%）\n\n"
            f"🎯 停利目標：\n"
            f"   第一目標：{tp1_price} 元\n"
            f"   理由：{tp1_reason}\n"
            f"   潛在獲利：{gain_at_tp1:+,.0f} 元（{gain_pct_tp1:+.1f}%）\n\n"
            f"   第二目標：{tp2_price} 元\n"
            f"   理由：{tp2_reason}\n"
            f"   潛在獲利：{gain_at_tp2:+,.0f} 元（{gain_pct_tp2:+.1f}%）\n\n"
            f"⚖️ 風險報酬比：1 : {rr_ratio}　風險等級：{risk_level}\n\n"
            f"💡 Smart 建議\n{summary}"
        )
        line.push_with_menu(uid, msg)

    except Exception as e:
        print(f"[risk] 風險評估失敗：{e}")
        line.push_with_menu(uid, "❌ 風險評估失敗，請稍後再試。")


def _handle_delete(uid, text, store, line, reply_token):
    # type: (str, str, object, object, str) -> None
    """處理刪除監控命令（格式：刪除 [數字]）"""
    try:
        # 解析數字：「刪除 1」→ 取得「1」
        parts = text.split()
        if len(parts) != 2:
            line.reply(reply_token, "❌ 格式錯誤。請輸入『刪除 [數字]』，例如：刪除 1")
            return

        index_str = parts[1]
        stock_index = int(index_str) - 1  # 轉換為 0-based 索引

        # 取得監控清單驗證索引
        watchlist = store.get_watchlist(uid)
        if not watchlist:
            line.reply(reply_token, "📊 你還沒有監控任何股票。")
            return

        if stock_index < 0 or stock_index >= len(watchlist):
            line.reply(reply_token, "❌ 索引超出範圍。請輸入 1 到 {} 之間的數字。".format(len(watchlist)))
            return

        # 取得要刪除的股票資訊
        stock = watchlist[stock_index]
        stock_id = stock.get("stock_id", "")
        stock_name = stock.get("stock_name", "")

        # 執行刪除
        store.remove_stock(uid, stock_index)

        line.reply(reply_token, "✅ 已刪除監控：{}（{}）".format(stock_name, stock_id))

    except ValueError:
        line.reply(reply_token, "❌ 請輸入有效的數字。例如：刪除 1")
    except Exception as e:
        line.reply(reply_token, "❌ 刪除失敗：{}".format(str(e)))
