"""
strategy.py — 連動雷達 + 出場指令判斷模組
依快照資料評估所有警報條件，回傳需發送的 Alert 列表
"""

from notifier import COLOR_INFO, COLOR_GREEN, COLOR_YELLOW, COLOR_RED


class Alert:
    """單筆警報資料類別"""

    def __init__(self, title: str, message: str, color: int):
        self.title = title
        self.message = message
        self.color = color


class StrategyEngine:
    """
    策略引擎：維護各警報的觸發狀態，確保同一警報不重複發送
    """

    def __init__(self, config: dict):
        self._config = config

        # 一次性警報旗標（True = 已觸發，不再重複）
        self.fired = {
            "watch":    False,  # 指令一：開盤看戲
            "stage1":   False,  # 指令二：保本落袋 2 張
            "stage2":   False,  # 指令三：清倉
            "stop":     False,  # 指令四：停損
            "us_alert": False,  # 美股利空鎖緊防守線
        }
        self.warned_peers = set()   # 已警示過的同業代號
        self.warned_group = set()   # 已警示過的集團股代號

        # 動態防守線，初始為 stop_loss_moving（63.0）
        self.current_stop = config["stop_loss_moving"]

    def evaluate(self, snap: dict) -> "list[Alert]":
        """
        依快照評估所有警報條件，回傳本次需發送的 Alert 列表
        price 為 None（盤前/斷線）時直接回傳空列表
        """
        price = snap["target"]["price"]
        if price is None:
            return []

        alerts = []
        cfg = self._config

        # --- 判斷 1：美股 AI 巨頭重挫 → 鎖緊防守線（一次性）---
        if not self.fired["us_alert"]:
            dropping_us = [
                (ticker, pct)
                for ticker, pct in snap["us"].items()
                if pct <= -cfg["us_drop_threshold_pct"]
            ]
            if dropping_us:
                self.fired["us_alert"] = True
                old_stop = self.current_stop
                self.current_stop = cfg["stop_loss_tightened"]

                lines = [f"  • {t}：{p:+.2f}%" for t, p in dropping_us]
                msg = (
                    "美股 AI 權值股出現重大跌幅：\n"
                    + "\n".join(lines)
                    + f"\n\n防守線由 {old_stop} 元調整至 {self.current_stop} 元。"
                    + "\n請提高警覺，隨時準備執行停損。"
                )
                alerts.append(Alert("美股 AI 巨頭重挫，防守線鎖緊", msg, COLOR_RED))

        # --- 判斷 2：台股同業重挫聯動（每個同業各一次）---
        for code, info in snap["peers"].items():
            if code not in self.warned_peers and info["pct"] <= -cfg["peer_drop_threshold_pct"]:
                self.warned_peers.add(code)
                msg = (
                    f"同業 {info['name']}（{code}）今日跌幅 {info['pct']:+.2f}%，"
                    f"已超過警戒門檻 -{cfg['peer_drop_threshold_pct']}%。\n"
                    f"請注意 3312 弘憶是否跟進賣壓。"
                )
                alerts.append(Alert("算力同業出現賣壓", msg, COLOR_YELLOW))

        # --- 判斷 3：集團資金撤退聯動（每個集團股各一次）---
        for code, info in snap["group"].items():
            if code not in self.warned_group and info["pct"] <= -cfg["group_drop_threshold_pct"]:
                self.warned_group.add(code)
                msg = (
                    f"集團股 {info['name']}（{code}）今日跌幅 {info['pct']:+.2f}%，"
                    f"已超過警戒門檻 -{cfg['group_drop_threshold_pct']}%。\n"
                    f"集團資金可能轉向，請注意弘憶連動風險。"
                )
                alerts.append(Alert("集團股走弱", msg, COLOR_YELLOW))

        limit_up = snap["target"]["limit_up"]
        limit_up_opened = snap["target"]["limit_up_opened"]
        total_volume = snap["target"]["total_volume"]

        # --- 判斷 4：指令一 — 開盤看戲（一字鎖漲停，一次性）---
        if (
            not self.fired["watch"]
            and limit_up is not None
            and price >= limit_up
            and not limit_up_opened
        ):
            self.fired["watch"] = True
            msg = (
                f"現價 {price} 元，已達漲停 {limit_up} 元，漲停板鎖死。\n"
                f"目前尚未打開，建議續抱看戲，不要急著賣出。"
            )
            alerts.append(Alert("開盤看戲：強勢鎖漲停", msg, COLOR_INFO))

        # --- 判斷 5：指令二 — 短線保本，落袋 2 張（一次性）---
        if not self.fired["stage1"]:
            condition_a = price >= cfg["target_stage_1"]
            condition_b = limit_up_opened and total_volume > cfg["alert_volume_threshold"]
            if condition_a or condition_b:
                self.fired["stage1"] = True
                alerts.append(
                    Alert(
                        "短線保本，落袋 2 張",
                        self._build_body(snap, "賣出 2 張，收回本金買保險！"),
                        COLOR_GREEN,
                    )
                )

        # --- 判斷 6：指令三 — 大獲全勝，狙擊 3 張（一次性）---
        if not self.fired["stage2"] and price >= cfg["target_stage_2"]:
            self.fired["stage2"] = True
            alerts.append(
                Alert(
                    "大獲全勝，狙擊 3 張",
                    self._build_body(
                        snap,
                        "已達 85 元估值天花板，全數獲利清倉，風光畢業！",
                    ),
                    COLOR_GREEN,
                )
            )

        # --- 判斷 7：指令四 — 智慧停利退場（動態防守線，一次性）---
        if not self.fired["stop"] and price <= self.current_stop:
            self.fired["stop"] = True
            alerts.append(
                Alert(
                    "智慧停利退場",
                    self._build_body(
                        snap,
                        f"已跌破防守死線 {self.current_stop} 元，建議將剩餘持股一次清空。",
                    ),
                    COLOR_RED,
                )
            )

        return alerts

    def _build_body(self, snap: dict, action: str) -> str:
        """
        建立警報訊息本文
        包含 3312 現況、同業、集團股、美股、防守線、操作指引
        """
        cfg = self._config
        target = snap["target"]
        price = target["price"]
        vol = target["total_volume"]
        limit_up = target["limit_up"]

        lines = []

        # 基本資訊
        lines.append(f"【3312 弘憶】現價 {price} 元（成本 {cfg['cost_price']}）")
        limit_str = f"{limit_up}" if limit_up else "N/A"
        lines.append(f"累計量 {vol} 張 ｜ 漲停 {limit_str} 元")

        # 同業（有資料才顯示）
        peer_parts = [
            f"{info['name']} {info['pct']:+.2f}%"
            for info in snap["peers"].values()
            if info["price"] is not None
        ]
        if peer_parts:
            lines.append("同業：" + " ｜ ".join(peer_parts))

        # 集團股（有資料才顯示）
        group_parts = [
            f"{info['name']} {info['pct']:+.2f}%"
            for info in snap["group"].values()
            if info["price"] is not None
        ]
        if group_parts:
            lines.append("集團：" + " ｜ ".join(group_parts))

        # 美股（有資料才顯示）
        us_parts = [
            f"{ticker} {pct:+.2f}%"
            for ticker, pct in snap["us"].items()
            if pct != 0.0
        ]
        if us_parts:
            lines.append("美股昨收：" + " ｜ ".join(us_parts))

        # 防守線與操作指引
        lines.append(f"目前生效防守線：{self.current_stop} 元")
        lines.append(f"👉 實戰指南：{action}")

        return "\n".join(lines)
