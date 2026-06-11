"""
telegram/keyboard.py — Inline Keyboard 產生器
回傳 list[list[dict]] 格式，供 TelegramClient 使用
"""
from typing import List


def main_menu_keyboard():
    # type: () -> List[List[dict]]
    """主選單 Inline Keyboard（2-2-1 排列）"""
    return [
        [
            {"text": "1️⃣ 股票監控", "callback_data": "1"},
            {"text": "2️⃣ 盤前分析", "callback_data": "2"},
        ],
        [
            {"text": "3️⃣ 盤後分析", "callback_data": "3"},
            {"text": "4️⃣ 選股推薦", "callback_data": "4"},
        ],
        [
            {"text": "5️⃣ ETF 推薦", "callback_data": "5"},
        ],
    ]


def cancel_keyboard():
    # type: () -> List[List[dict]]
    """問答流程中的取消按鈕"""
    return [
        [{"text": "❌ 取消", "callback_data": "cancel"}],
    ]


def to_inline_markup(keyboard):
    # type: (List[List[dict]]) -> dict
    """將 list[list[dict]] 轉為 Telegram InlineKeyboardMarkup dict"""
    return {
        "inline_keyboard": [
            [
                {"text": btn["text"], "callback_data": btn["callback_data"]}
                for btn in row
            ]
            for row in keyboard
        ]
    }
