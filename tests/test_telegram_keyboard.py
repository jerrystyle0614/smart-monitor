"""test_telegram_keyboard.py — Telegram Inline Keyboard 單元測試"""


def test_main_menu_keyboard_has_5_services():
    """主選單應有 5 個服務按鈕"""
    from bot.telegram.keyboard import main_menu_keyboard
    kb = main_menu_keyboard()
    buttons = [btn for row in kb for btn in row]
    assert len(buttons) == 5


def test_main_menu_keyboard_callback_data():
    """每個按鈕的 callback_data 應對應 1-5"""
    from bot.telegram.keyboard import main_menu_keyboard
    kb = main_menu_keyboard()
    datas = [btn["callback_data"] for row in kb for btn in row]
    assert set(datas) == {"1", "2", "3", "4", "5"}


def test_cancel_keyboard_has_one_button():
    """取消鍵盤應只有一個 ❌ 取消 按鈕"""
    from bot.telegram.keyboard import cancel_keyboard
    kb = cancel_keyboard()
    buttons = [btn for row in kb for btn in row]
    assert len(buttons) == 1
    assert buttons[0]["callback_data"] == "cancel"


def test_to_inline_markup_structure():
    """to_inline_markup 應轉換為正確的 Telegram markup 格式"""
    from bot.telegram.keyboard import cancel_keyboard, to_inline_markup
    markup = to_inline_markup(cancel_keyboard())
    assert "inline_keyboard" in markup
    assert markup["inline_keyboard"][0][0]["callback_data"] == "cancel"
