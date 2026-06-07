"""
router.py — ServiceRouter 主路由模組
路由使用者訊息到對應的服務或選單
"""

from typing import Optional, Dict, List

from bot.services.stock_monitor import StockMonitorService
from bot.services.pre_market import PreMarketService
from bot.services.post_market import PostMarketService
from bot.services.stock_picker import StockPickerService


SERVICE_PERMISSIONS = {
    "stock_monitor": ["free", "basic", "pro"],
    "pre_market":    ["basic", "pro"],
    "post_market":   ["basic", "pro"],
    "stock_picker":  ["pro"],
}

_ADD_STOCK = StockMonitorService()
_PRE_MARKET = PreMarketService()
_POST_MARKET = PostMarketService()
_STOCK_PICKER = StockPickerService()

_SERVICE_MAP = {
    "stock_monitor": _ADD_STOCK,
    "pre_market": _PRE_MARKET,
    "post_market": _POST_MARKET,
    "stock_picker": _STOCK_PICKER,
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
    """處理追蹤事件"""
    store.set_plan(uid, "free")
    line.push(uid,
        "👋 歡迎使用 Smart Monitor！\n\n"
        "我是您的台股投資小助手。\n"
        "提供股票監控、盤前/盤後分析等功能。"
    )
    line.push(uid, "輸入『狀態』查看監控清單，或輸入數字選擇服務。")


def handle_message(uid, text, store, line, reply_token):
    # type: (str, str, object, object, str) -> None
    """
    處理訊息。主路由邏輯：
    1. 冷卻檢查
    2. 問答進行中 → 交給服務處理
    3. stock_monitor_confirm 狀態 → 等待確認
    4. 其他 → 顯示選單或解析命令
    """
    text = text.strip()

    # 冷卻檢查
    if store.check_cooldown(uid):
        line.reply("⏱️ 傳送訊息過於頻繁，請稍後再試。")
        return

    # 檢查問答是否進行中
    current_service = store.get_current_service(uid)

    # 等待股票監控確認
    if current_service == "stock_monitor_confirm":
        _handle_stock_confirm(uid, text, store, line, reply_token)
        return

    # 其他服務問答進行中
    if current_service is not None:
        _route_to_service(uid, text, current_service, store, line, reply_token)
        return

    # 主菜單路由
    if text in ("1", "2", "3", "4"):
        _handle_menu(uid, text, store, line, reply_token)
    elif text in ("狀態", "status"):
        _show_watchlist(uid, store, line, reply_token)
    elif text in ("說明", "help"):
        _show_help(uid, line, reply_token)
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
    }

    service_name, service = service_map.get(choice, (None, None))
    if not service_name:
        _show_menu(uid, store, line, reply_token)
        return

    # 檢查權限
    allowed_plans = SERVICE_PERMISSIONS.get(service_name, [])
    if plan not in allowed_plans:
        if service_name == "stock_picker":
            line.reply(reply_token,
                "⚠️ 選股推薦為 pro 方案專屬功能。\n"
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
        "📊 Smart Monitor\n\n"
        "請選擇服務：\n"
        "1️⃣ 股票監控\n"
    )

    if plan in ("basic", "pro"):
        menu += "2️⃣ 盤前分析\n"
        menu += "3️⃣ 盤後分析\n"

    if plan == "pro":
        menu += "4️⃣ 選股推薦\n"

    menu += "\n輸入數字選擇，或輸入『狀態』查看目前監控\n"
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
        cost = stock.get("cost_price")
        stop_loss = stock.get("stop_loss_moving")

        msg += "{} {}（{}）\n".format(i, stock_name, stock_id)
        msg += "   均價 {} 元".format(cost)
        if stop_loss:
            msg += " | 停損 {} 元".format(stop_loss)
        msg += "\n"

    msg += "\n可用指令：新增 / 修改 [數字] / 刪除 [數字]"
    line.reply(reply_token, msg)


def _show_help(uid, line, reply_token):
    # type: (str, object, str) -> None
    """顯示使用說明"""
    msg = (
        "📖 使用說明\n\n"
        "1️⃣ 股票監控\n"
        "   監控股票價格，達停損/目標價推播\n\n"
        "2️⃣ 盤前分析\n"
        "   獲取股票盤前技術面分析\n\n"
        "3️⃣ 盤後分析\n"
        "   獲取股票盤後技術面分析\n\n"
        "『狀態』查看監控清單\n"
        "『說明』查看此說明"
    )
    line.reply(reply_token, msg)
