"""
mock_stocks.py — 臨時的股票資料快取，用於測試當 Fugle API 不可用時
生產環境應移除此檔案，改用真實 Fugle API
"""

MOCK_STOCKS = {
    "台積電": "2330",
    "2330": {"stock_id": "2330", "stock_name": "台積電"},
    "聯發科": "2454",
    "2454": {"stock_id": "2454", "stock_name": "聯發科"},
    "鴻海": "2317",
    "2317": {"stock_id": "2317", "stock_name": "鴻海"},
    "智易科技": "3312",
    "3312": {"stock_id": "3312", "stock_name": "智易科技"},
    "世芯": "3661",
    "3661": {"stock_id": "3661", "stock_name": "世芯"},
    "宏達電": "2498",
    "2498": {"stock_id": "2498", "stock_name": "宏達電"},
    "台灣大": "3045",
    "3045": {"stock_id": "3045", "stock_name": "台灣大"},
    "中華電": "2412",
    "2412": {"stock_id": "2412", "stock_name": "中華電"},
    "光達": "3714",
    "3714": {"stock_id": "3714", "stock_name": "光達"},
    "日月光": "3711",
    "3711": {"stock_id": "3711", "stock_name": "日月光"},
}

MOCK_QUOTES = {
    "2330": {"stock_id": "2330", "stock_name": "台積電", "close_price": 920.0, "change_pct": -0.84},
    "2454": {"stock_id": "2454", "stock_name": "聯發科", "close_price": 1350.0, "change_pct": 1.50},
    "2317": {"stock_id": "2317", "stock_name": "鴻海", "close_price": 230.0, "change_pct": -0.43},
    "3312": {"stock_id": "3312", "stock_name": "智易科技", "close_price": 45.65, "change_pct": 2.30},
    "3661": {"stock_id": "3661", "stock_name": "世芯", "close_price": 180.0, "change_pct": -1.10},
    "2498": {"stock_id": "2498", "stock_name": "宏達電", "close_price": 75.50, "change_pct": 0.67},
    "3045": {"stock_id": "3045", "stock_name": "台灣大", "close_price": 102.0, "change_pct": -0.49},
    "2412": {"stock_id": "2412", "stock_name": "中華電", "close_price": 28.35, "change_pct": 1.43},
    "3714": {"stock_id": "3714", "stock_name": "光達", "close_price": 185.0, "change_pct": -0.54},
    "3711": {"stock_id": "3711", "stock_name": "日月光", "close_price": 108.0, "change_pct": 1.12},
}
