# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Data models shared between strategies, harness, and platform runtimes."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


@dataclass(slots=True)
class Candle:
    """OHLCV bar. Timestamps are exchange-provided milliseconds since epoch."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def is_bullish(self) -> bool:
        return self.close > self.open

    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0


class SignalSide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass(slots=True)
class Signal:
    """Entry signal emitted by a strategy. `rule_id` is free-form — strategies
    that fire from multiple decision rules can encode which one matched.
    Optional fields default to platform-resolved values when omitted."""

    side: SignalSide
    rule_id: int = 1
    stop_loss: float = 0.0
    reward_ratio: float = 0.0
    leverage: int = 0
    risk_multiplier: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TradeResult:
    """Closed-trade outcome surfaced back to strategies for stateful sizing
    (e.g. anti-martingale / double-on-win). PnL is in quote currency (USDT)."""

    side: SignalSide
    entry_price: float
    exit_price: float
    pnl: float
    fees: float = 0.0
    won: bool = False
    closed_at: int = 0  # epoch ms
