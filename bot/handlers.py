"""
handlers.py — LINE Bot 事件處理邏輯
follow 事件推播歡迎訊息；message 事件依狀態機路由
"""

from typing import Optional
from bot.claude_parser import parse_monitor_intent, is_monitor_intent, chat_reply
from bot.state_machine import StateMachine, FIELD_QUESTIONS
from bot.user_store import (
    INTENT_FAIL_GUIDE, INTENT_FAIL_WARN, INTENT_FAIL_BLOCK,
    COOLDOWN_BLOCK_SEC,
)

# 每日 Claude API 呼叫次數上限，防止意外大量消耗 token
DAILY_CALL_LIMIT = 10

# 歡迎訊息（加好友時推播兩則）
WELCOME_MSG_1 = """👋 你好！我是 Smart 股市助理。

我能幫你：
• 監控個股即時條件（停損、目標價到達立即通知）
• 每日 08:30 盤前分析（今日技術面摘要）
• 每日 13:35 盤後分析（明日進出場建議）

⚠️ 所有對話只有你和我，其他人看不到。
📌 本助理依你設定的條件發送提醒，不構成投資建議。"""

WELCOME_MSG_2 = """📖 使用方式

【開始監控】
直接告訴我，你的狀況，例如：
「我買了弘憶 x 張，均價 xx 元，停損 xx 元」

確認條件前可直接修改，例如：
「修改股票 台積電」「修改持股 5」「修改均價 62」
「修改停損 60」「修改目標 80」「修改目標二 90」

【管理監控】
狀態　　　→ 查看目前監控條件
修改停損 62 → 修改停損價
修改目標 80 → 修改目標價
停止　　　→ 停止監控

如需協助請輸入「說明」"""

HELP_MSG = """可用指令：
• 狀態 — 查看監控條件
• 修改停損 [價格] — 修改停損價
• 修改目標 [價格] — 修改目標價
• 停止 — 停止監控

輸入你的持股狀況即可開始監控，例如：
「我買了弘憶 5 張，均價 64.86，停損 63 元」"""


def handle_follow(user_id: str, store, line) -> None:
    """處理加好友事件，推播兩則歡迎訊息"""
    line.push(user_id, WELCOME_MSG_1)
    line.push(user_id, WELCOME_MSG_2)


def handle_message(user_id: str, text: str, store, line,
                   reply_token: str = "mock_token") -> None:
    """處理訊息事件，依當前對話狀態路由到對應邏輯"""
    state = store.get_state(user_id)
    text = text.strip()

    # --- MONITORING 狀態的管理指令 ---
    if state == "MONITORING":
        if text in ("停止", "stop"):
            # 停止監控，清除 config，回到 IDLE
            store.set_state(user_id, "IDLE")
            store.set_config(user_id, {})
            line.reply(reply_token, "✅ 已停止監控。")
            return
        if text in ("狀態", "status"):
            # 查看目前監控條件
            cfg = store.get_config(user_id)
            _reply_status(reply_token, cfg, line)
            return
        if text.startswith("修改停損"):
            # 修改動態防守線（停損價）
            _handle_update(user_id, text, "stop_loss_moving", reply_token, store, line)
            return
        if text.startswith("修改目標"):
            # 修改目標一價格
            _handle_update(user_id, text, "target_stage_1", reply_token, store, line)
            return
        if text in ("測試分析", "test"):
            # 立即觸發一次盤前分析，用於測試（不受交易時段限制）
            from bot.analysis_runner import run_analysis_for_user, AnalysisMode
            import json as _json
            cfg = store.get_config(user_id)
            swing_cfg = {}
            try:
                with open("config.json", encoding="utf-8") as f:
                    swing_cfg = _json.load(f)
            except Exception:
                pass
            result = run_analysis_for_user(cfg, swing_cfg, AnalysisMode.PREMARKET)
            if result:
                from notifier import DiscordNotifier
                line.reply(reply_token, f"{result['title']}\n\n{result['message']}")
                DiscordNotifier().send(result["title"], result["message"], result["color"])
                for alert in result["alerts"]:
                    line.push(user_id, f"{alert.title}\n\n{alert.message}")
                    DiscordNotifier().send(alert.title, alert.message, alert.color)
            else:
                line.reply(reply_token, "⚠️ 分析失敗，請確認股票代號是否正確。")
            return
        # 其他訊息一律回覆操作說明
        line.reply(reply_token, HELP_MSG)
        return

    # --- CONFIRMING 狀態：等待使用者確認解析結果 ---
    if state == "CONFIRMING":
        if text in ("確認", "yes", "ok", "好"):
            cfg = store.get_config(user_id)
            # stock_id 未知時拒絕確認，要求使用者手動補填代號
            if not cfg.get("stock_id"):
                line.reply(reply_token,
                           f"⚠️ 找不到「{cfg.get('stock_name','')}」的股票代號，\n"
                           f"請手動補填，例如：修改股票代號 6285")
                return
            store.set_state(user_id, "MONITORING")
            line.reply(reply_token,
                       f"✅ 已開始監控 {cfg.get('stock_id','')} {cfg.get('stock_name','')}，"
                       f"條件達成時會通知你。\n\n可用指令：狀態 ／ 修改停損 X ／ 停止")
            # 確認後立即推播一次盤前分析，讓使用者馬上看到當前技術面
            _push_analysis_once(user_id, cfg, line)
        elif text in ("重新輸入", "cancel", "取消"):
            # 使用者取消，回到 IDLE 重新輸入
            store.set_state(user_id, "IDLE")
            line.reply(reply_token, "已取消，請重新輸入監控條件。")
        elif _try_confirm_edit_multi(user_id, text, store):
            # 使用者一次修改多個欄位（逗號分隔），全部套用後重新顯示卡片
            cfg = store.get_config(user_id)
            sm = StateMachine()
            sm.pending_config = cfg
            line.reply(reply_token, _confirm_card(sm))
        elif _try_confirm_edit(user_id, text, store):
            # 使用者修改單一欄位，重新顯示更新後的確認卡片
            cfg = store.get_config(user_id)
            sm = StateMachine()
            sm.pending_config = cfg
            line.reply(reply_token, _confirm_card(sm))
        elif is_monitor_intent(text):
            # 使用者重新輸入完整監控條件，重新解析並覆蓋舊 config
            parsed = parse_monitor_intent(text)
            store.set_config(user_id, parsed)
            sm = StateMachine()
            sm.pending_config = parsed
            missing = sm.get_missing_fields()
            if missing:
                store.set_state(user_id, "COLLECTING")
                sm.current_question = missing[0]
                store.set_current_question(user_id, sm.current_question)
                line.reply(reply_token, sm.next_question())
            else:
                line.reply(reply_token, _confirm_card(sm))
        else:
            # 其他回應重新顯示確認卡片
            cfg = store.get_config(user_id)
            sm = StateMachine()
            sm.pending_config = cfg
            line.reply(reply_token, _confirm_card(sm))
        return

    # --- COLLECTING 狀態：追問缺少的必填欄位 ---
    if state == "COLLECTING":
        cfg = store.get_config(user_id)
        sm = StateMachine()
        sm.state = "COLLECTING"
        sm.pending_config = dict(cfg)

        # 還原 current_question（從 store 的 state 資料讀取）
        sm.current_question = store.get_current_question(user_id)

        success = sm.apply_answer(text)
        if not success:
            # 使用者輸入格式錯誤，重問同一個問題
            question = FIELD_QUESTIONS.get(sm.current_question, "請再輸入一次")
            line.reply(reply_token, f"格式錯誤，請輸入數字。{question}")
            return

        # 儲存已更新的 config
        store.set_config(user_id, sm.pending_config)
        missing = sm.get_missing_fields()
        if missing:
            # 仍有未填欄位，繼續追問下一個
            sm.current_question = missing[0]
            store.set_current_question(user_id, sm.current_question)
            line.reply(reply_token, sm.next_question())
        else:
            # 所有必填欄位齊全，切換到確認狀態
            store.set_state(user_id, "CONFIRMING")
            line.reply(reply_token, _confirm_card(sm))
        return

    # --- IDLE 狀態：由 Claude 判斷是否為監控意圖 ---
    sm = StateMachine()

    # 管理指令直接處理，不送 Claude
    if text in ("說明", "help", "狀態", "status", "重新輸入", "cancel", "取消"):
        line.reply(reply_token, HELP_MSG)
        return

    # 冷卻機制：30 秒內超過 5 則觸發 60 秒封鎖
    if store.check_cooldown(user_id):
        line.reply(reply_token,
                   f"你傳送訊息的速度太快了，請等待 {COOLDOWN_BLOCK_SEC} 秒後再試。")
        return

    # 意圖失敗惡意攻擊攔截（失敗 20 次以上，當日不再處理）
    fail_count = store.get_daily_intent_fail_count(user_id)
    if fail_count >= INTENT_FAIL_BLOCK:
        line.reply(reply_token, "今日已達詢問上限，請明天再試。")
        return

    # 監控設定每日呼叫上限
    count = store.get_daily_call_count(user_id)
    if count >= DAILY_CALL_LIMIT:
        line.reply(reply_token,
                   f"今日監控設定次數已達上限（{DAILY_CALL_LIMIT} 次），請明天再試。")
        return

    # 先讓 Claude 判斷是否為監控意圖
    print(f"[handlers] IDLE 收到訊息，fail_count={fail_count}, call_count={count}, text={text[:50]}")
    if not is_monitor_intent(text):
        fail_count = store.increment_intent_fail_count(user_id)

        if fail_count >= INTENT_FAIL_WARN:
            # 第 10~19 次：警告有上限
            line.reply(reply_token,
                       f"⚠️ 今日有效詢問次數剩餘 {INTENT_FAIL_BLOCK - fail_count} 次。\n"
                       f"請輸入股票監控條件，例如：\n"
                       f"「我買了台積電 1 張，均價 950，停損 900」")
        elif fail_count >= INTENT_FAIL_GUIDE:
            # 第 5~9 次：給範例引導
            line.reply(reply_token,
                       "我主要負責股票監控設定 📊\n\n"
                       "可以這樣輸入：\n"
                       "「我買了弘憶 5 張，均價 64.86，停損 63」\n\n"
                       "輸入「說明」查看完整指令。")
        else:
            # 第 1~4 次：Claude 自然語言回覆
            line.reply(reply_token, chat_reply(text))
        return

    # 是監控意圖，呼叫 Claude 解析欄位（消耗監控設定額度）
    store.increment_daily_call_count(user_id)
    parsed = parse_monitor_intent(text)
    store.set_config(user_id, parsed)
    sm.pending_config = parsed

    missing = sm.get_missing_fields()
    if missing:
        # 有必填欄位缺失，進入追問流程
        store.set_state(user_id, "COLLECTING")
        sm.current_question = missing[0]
        store.set_current_question(user_id, sm.current_question)
        line.reply(reply_token, sm.next_question())
    else:
        # 所有欄位齊全，進入確認流程
        store.set_state(user_id, "CONFIRMING")
        line.reply(reply_token, _confirm_card(sm))


def _reply_status(reply_token: str, cfg: dict, line) -> None:
    """推播目前監控條件摘要"""
    if not cfg:
        line.reply(reply_token, "目前沒有進行中的監控。")
        return
    shares = cfg.get("total_shares", 0)
    lots = shares // 1000 if shares else 0
    msg = (
        f"📊 監控中：{cfg.get('stock_id','')} {cfg.get('stock_name','')}\n"
        f"持股：{lots} 張，均價：{cfg.get('cost_price','')} 元\n"
        f"停損：{cfg.get('stop_loss_moving','未設定')} 元\n"
        f"目標一：{cfg.get('target_stage_1','未設定')} 元"
    )
    line.reply(reply_token, msg)


def _fetch_close(stock_id: str) -> tuple:
    """從 Fugle 查詢最新收盤價與漲跌幅，回傳 (close_price, change_pct)，失敗回傳 (None, None)"""
    import requests, os
    api_key = os.environ.get("FUGLE_API_KEY")
    if not api_key or not stock_id:
        return None, None
    try:
        r = requests.get(
            f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{stock_id}",
            headers={"X-API-KEY": api_key},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            close = data.get("closePrice") or data.get("lastPrice")
            pct = data.get("changePercent")
            return close, pct
    except Exception as e:
        print(f"[警告] 查詢收盤價失敗：{e}")
    return None, None


def _confirm_card(sm) -> str:
    """查詢收盤價後建立確認卡片"""
    stock_id = sm.pending_config.get("stock_id")
    close, pct = _fetch_close(stock_id)
    return sm.build_confirm_card(close_price=close, change_pct=pct)


def _resolve_stock(value_str: str) -> Optional[dict]:
    """
    用 Fugle 本地股票對照表將名稱或代號解析為 {stock_id, stock_name}。
    找不到回傳 None，不再依賴 AI 猜測。
    """
    from bot.claude_parser import _STOCK_MAP
    value_str = value_str.strip()

    # 先嘗試把 value_str 當成代號，反查名稱
    reverse_map = {v: k for k, v in _STOCK_MAP.items()}
    if value_str in reverse_map:
        return {"stock_id": value_str, "stock_name": reverse_map[value_str]}

    # 再嘗試完整名稱比對
    if value_str in _STOCK_MAP:
        return {"stock_id": _STOCK_MAP[value_str], "stock_name": value_str}

    # 最後嘗試部分名稱比對（輸入的字是名稱的子字串）
    for name, symbol in _STOCK_MAP.items():
        if value_str in name:
            print(f"[_resolve_stock] 部分比對：{value_str} → {symbol} {name}")
            return {"stock_id": symbol, "stock_name": name}

    print(f"[_resolve_stock] 找不到：{value_str}")
    return None


def _try_confirm_edit_multi(user_id: str, text: str, store) -> bool:
    """
    處理逗號分隔的多欄位修改指令，例如「修改持股1，修改均價90，修改停損40」。
    所有片段都能被 _try_confirm_edit 識別才套用，否則回傳 False 不做任何修改。
    """
    import re
    # 用中文逗號或英文逗號分割
    parts = [p.strip() for p in re.split(r'[，,]', text) if p.strip()]
    # 至少要有 2 個片段才算多欄位修改（單一片段交給原本的 _try_confirm_edit 處理）
    if len(parts) < 2:
        return False
    # 每個片段都必須以「修改」開頭或是已知的欄位別名才處理，否則視為完整句子不攔截
    KNOWN_PREFIXES = ("修改", "均價", "成本", "停損", "持股", "張數", "目標")
    if not all(any(p.startswith(prefix) for prefix in KNOWN_PREFIXES) for p in parts):
        return False
    # 在暫存副本上逐一套用，全部成功才寫入
    import copy, json as _json
    from pathlib import Path
    cfg = store.get_config(user_id)
    tmp_cfg = copy.deepcopy(cfg)
    tmp_store = type('TmpStore', (), {
        'get_config': lambda self, uid: tmp_cfg,
        'set_config': lambda self, uid, c: tmp_cfg.update(c),
    })()
    for part in parts:
        if not _try_confirm_edit(user_id, part, tmp_store):
            return False
    # 全部成功，寫回真實 store
    store.set_config(user_id, tmp_cfg)
    return True


def _try_confirm_edit(user_id: str, text: str, store) -> bool:
    """
    在 CONFIRMING 狀態解析修改指令，更新 config 後回傳 True。
    無法辨識或解析失敗時回傳 False，不修改任何資料。
    支援格式：修改均價 62 ／ 修改停損 63 ／ 修改張數 3 ／ 修改目標 75 ／ 修改目標二 85
    """
    # 欄位別名對應表（較長的別名必須排在前面，避免「目標」比「目標二」先匹配）
    # 數值型欄位（支援「修改停損 90」和「停損90」兩種格式）
    NUMERIC_ALIASES = {
        "均價": "cost_price",
        "成本": "cost_price",
        "停損": "stop_loss_moving",
        "持股": "total_shares",
        "張數": "total_shares",
        "目標二": "target_stage_2",
        "目標一": "target_stage_1",
        "目標": "target_stage_1",
    }
    # 字串型欄位別名（較長的排前面）
    # "股票" 後面接名稱時，同時更新 stock_id 和 stock_name
    STRING_ALIASES = {
        "股票代號": "stock_id",   # 只更新代號
        "股票名稱": "stock_name", # 只更新名稱
        "代號": "stock_id",
        "名稱": "stock_name",
        "股票": "stock_both",     # 輸入名稱或代號，自動解析兩者
    }

    # 支援「修改停損 90」和「停損90」兩種格式
    if text.startswith("修改"):
        body = text[2:].strip()
    else:
        body = text  # 直接用欄位別名開頭

    # 先嘗試字串型欄位（stock_id / stock_name）
    for alias, field in STRING_ALIASES.items():
        if body.startswith(alias):
            value_str = body[len(alias):].strip()
            if not value_str:
                return False
            cfg = store.get_config(user_id)
            if field == "stock_both":
                # 使用者只說名稱或代號，用 Claude 解析完整股票資訊
                parsed = _resolve_stock(value_str)
                if parsed:
                    cfg["stock_id"] = parsed["stock_id"]
                    cfg["stock_name"] = parsed["stock_name"]
                else:
                    # Claude 解析失敗，存名稱但 stock_id 設為 null，讓使用者手動補代號
                    cfg["stock_name"] = value_str
                    cfg["stock_id"] = None
                # 換股票後所有價格條件不再適用，一律清除
                cfg["cost_price"] = None
                cfg["total_shares"] = None
                cfg["stop_loss_moving"] = None
                cfg["target_stage_1"] = None
                cfg["target_stage_2"] = None
            else:
                cfg[field] = value_str
                # 換股票後所有價格條件不再適用，一律清除
                if field in ("stock_id", "stock_name"):
                    cfg["cost_price"] = None
                    cfg["total_shares"] = None
                    cfg["stop_loss_moving"] = None
                    cfg["target_stage_1"] = None
                    cfg["target_stage_2"] = None
            store.set_config(user_id, cfg)
            return True

    # 再嘗試數值型欄位
    matched_field = None
    value_str = None
    for alias, field in NUMERIC_ALIASES.items():
        if body.startswith(alias):
            matched_field = field
            value_str = body[len(alias):].strip().replace("元", "").replace("張", "")
            break

    if matched_field is None or not value_str:
        return False

    try:
        cfg = store.get_config(user_id)
        if matched_field == "total_shares":
            cfg[matched_field] = int(float(value_str) * 1000)  # 張 → 股
        else:
            cfg[matched_field] = float(value_str)
        store.set_config(user_id, cfg)
        return True
    except ValueError:
        return False


def _handle_update(user_id: str, text: str, field: str,
                   reply_token: str, store, line) -> None:
    """處理修改停損/目標指令，解析數字後更新 config"""
    cfg = store.get_config(user_id)
    if not cfg:
        line.reply(reply_token, "目前沒有監控設定，請先設定監控條件。")
        return
    try:
        parts = text.split()
        value = float(parts[-1].replace("元", ""))
        cfg[field] = value
        store.set_config(user_id, cfg)
        store.reset_alerts(user_id)
        label = "停損" if field == "stop_loss_moving" else "目標"
        line.reply(reply_token,
                   f"✅ 已更新{label}價為 {value} 元，30 秒內生效。\n\n"
                   f"可用指令：狀態 ／ 修改停損 X ／ 修改目標 X ／ 停止")
    except (ValueError, IndexError):
        line.reply(reply_token, "格式錯誤，請輸入如：修改停損 62")


def _push_analysis_once(user_id: str, cfg: dict, line) -> None:
    """確認監控後立即推播一次盤前分析到 LINE + Discord。
    失敗只印警告，不影響主流程。"""
    import json as _json
    from bot.analysis_runner import run_analysis_for_user, AnalysisMode
    from notifier import DiscordNotifier
    try:
        swing_cfg = {}
        try:
            with open("config.json", encoding="utf-8") as f:
                swing_cfg = _json.load(f)
        except Exception:
            pass
        result = run_analysis_for_user(cfg, swing_cfg, AnalysisMode.PREMARKET)
        if result:
            discord = DiscordNotifier()
            line.push(user_id, f"{result['title']}\n\n{result['message']}")
            discord.send(result["title"], result["message"], result["color"])
            for alert in result["alerts"]:
                line.push(user_id, f"{alert.title}\n\n{alert.message}")
                discord.send(alert.title, alert.message, alert.color)
    except Exception as e:
        print(f"[handlers] 確認後分析推播失敗：{e}")
