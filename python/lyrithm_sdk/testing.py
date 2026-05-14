# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""
Local backtest harness — no cloud, no exchange, no DB. Run a strategy over a
CSV / list of candles and inspect the signals it would have produced.

This is intentionally *minimal*. For full backtests with fee / slippage /
position tracking, publish your strategy and run it through lyrithm-sandbox.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from .models import Candle, SignalSide
from .strategy import Strategy


@dataclass
class SignalRecord:
    timestamp: int
    side: SignalSide
    rule_id: int
    price: float
    stop_loss: float
    reward_ratio: float
    leverage: int
    risk_multiplier: float
    adx: float


@dataclass
class BacktestReport:
    candles_processed: int = 0
    signals: List[SignalRecord] = field(default_factory=list)

    @property
    def long_signals(self) -> List[SignalRecord]:
        return [s for s in self.signals if s.side == SignalSide.LONG]

    @property
    def short_signals(self) -> List[SignalRecord]:
        return [s for s in self.signals if s.side == SignalSide.SHORT]

    def summary(self) -> str:
        return (
            f"candles_processed={self.candles_processed}  "
            f"signals={len(self.signals)} "
            f"(long={len(self.long_signals)}, short={len(self.short_signals)})"
        )


class BacktestRunner:
    """Drives a Strategy through a stream of candles and records every signal
    via the existing Strategy contract (`check_long_entry` / `check_short_entry`)."""

    def __init__(self, strategy: Strategy):
        self.strategy = strategy

    def run(self, candles: Iterable[Candle]) -> BacktestReport:
        report = BacktestReport()
        for candle in candles:
            self.strategy.update(candle)
            report.candles_processed += 1
            if not self.strategy.is_ready():
                continue

            long_rule = self.strategy.check_long_entry()
            if long_rule:
                report.signals.append(
                    SignalRecord(
                        timestamp=candle.timestamp,
                        side=SignalSide.LONG,
                        rule_id=long_rule,
                        price=candle.close,
                        stop_loss=self.strategy.calculate_long_stop_loss(),
                        reward_ratio=self.strategy.get_dynamic_reward_ratio(),
                        leverage=self.strategy.get_dynamic_leverage(),
                        risk_multiplier=self.strategy.get_dynamic_risk_multiplier(),
                        adx=self.strategy.get_adx(),
                    )
                )
                continue

            short_rule = self.strategy.check_short_entry()
            if short_rule:
                report.signals.append(
                    SignalRecord(
                        timestamp=candle.timestamp,
                        side=SignalSide.SHORT,
                        rule_id=short_rule,
                        price=candle.close,
                        stop_loss=self.strategy.calculate_short_stop_loss(),
                        reward_ratio=self.strategy.get_dynamic_reward_ratio(),
                        leverage=self.strategy.get_dynamic_leverage(),
                        risk_multiplier=self.strategy.get_dynamic_risk_multiplier(),
                        adx=self.strategy.get_adx(),
                    )
                )

        return report


def load_candles_csv(path: Path) -> List[Candle]:
    """Load OHLCV candles from a CSV with columns: timestamp,open,high,low,close,volume.
    Timestamp accepts either epoch ms (int) or ISO-8601 (str)."""
    import datetime as dt

    candles: List[Candle] = []
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing columns: {sorted(missing)}")
        for row in reader:
            ts_raw = row["timestamp"].strip()
            if ts_raw.isdigit():
                ts = int(ts_raw)
            else:
                ts = int(dt.datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp() * 1000)
            candles.append(
                Candle(
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    return candles
