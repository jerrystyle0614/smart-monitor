"""
handlers.py — LINE Bot 事件處理邏輯
follow 事件推播歡迎訊息；message 事件依狀態機路由
"""

from bot.claude_parser import parse_monitor_intent
from bot.state_machine import StateMachine, FIELD_QUESTIONS

# 每日 Claude API 呼叫次數上限，防止意外大量消耗 token
DAILY_CALL_LIMIT = 10

# 歡迎訊息（加好友時推播兩則）
WELCOME_MSG_1 = """👋 你好！我是 AI 股票監控助理。

我能幫你：
• 監控個股即時條件（停損、目標價到達立即通知）
• 每日 08:30 盤前分析（今日技術面摘要）
• 每日 13:35 盤後分析（明日進出場建議）

⚠️ 所有對話只有你和我，其他人看不到。
📌 本助理依你設定的條件發送提醒，不構成投資建議。"""

WELCOME_MSG_2 = """📖 使用方式

【開始監控】
直接用自然語言告訴我你的持股狀況，例如：
「我買了弘憶 5 張，均價 64.86，停損 63 元」

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
        # 其他訊息一律回覆操作說明
        line.reply(reply_token, HELP_MSG)
        return

    # --- CONFIRMING 狀態：等待使用者確認解析結果 ---
    if state == "CONFIRMING":
        if text in ("確認", "yes", "ok", "好"):
            # 使用者確認，切換到 MONITORING 狀態
            cfg = store.get_config(user_id)
            store.set_state(user_id, "MONITORING")
            line.reply(reply_token,
                       f"✅ 已開始監控 {cfg.get('stock_id','')} {cfg.get('stock_name','')}，"
                       f"條件達成時會通知你。\n\n可用指令：狀態 ／ 修改停損 X ／ 停止")
        elif text in ("重新輸入", "cancel", "取消"):
            # 使用者取消，回到 IDLE 重新輸入
            store.set_state(user_id, "IDLE")
            line.reply(reply_token, "已取消，請重新輸入監控條件。")
        else:
            # 其他回應重新顯示確認卡片
            cfg = store.get_config(user_id)
            sm = StateMachine()
            sm.pending_config = cfg
            line.reply(reply_token, sm.build_confirm_card())
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
            line.reply(reply_token, sm.build_confirm_card())
        return

    # --- IDLE 狀態：判斷是否為監控意圖，否則回覆說明 ---
    sm = StateMachine()
    if not sm.should_parse(text):
        # 非監控相關訊息，回覆操作說明
        line.reply(reply_token, HELP_MSG)
        return

    # 檢查每日 Claude 呼叫上限，超過則拒絕
    count = store.get_daily_call_count(user_id)
    if count >= DAILY_CALL_LIMIT:
        line.reply(reply_token,
                   f"今日解析次數已達上限（{DAILY_CALL_LIMIT} 次），請明天再試。")
        return

    # 呼叫 Claude 解析使用者輸入
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
        line.reply(reply_token, sm.build_confirm_card())


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


def _handle_update(user_id: str, text: str, field: str,
                   reply_token: str, store, line) -> None:
    """處理修改停損/目標指令，解析數字後更新 config"""
    try:
        parts = text.split()
        value = float(parts[-1].replace("元", ""))
        cfg = store.get_config(user_id)
        cfg[field] = value
        store.set_config(user_id, cfg)
        label = "停損" if field == "stop_loss_moving" else "目標"
        line.reply(reply_token,
                   f"✅ 已更新{label}價為 {value} 元，5 秒內生效。\n\n"
                   f"可用指令：狀態 ／ 修改停損 X ／ 修改目標 X ／ 停止")
    except (ValueError, IndexError):
        line.reply(reply_token, "格式錯誤，請輸入如：修改停損 62")
