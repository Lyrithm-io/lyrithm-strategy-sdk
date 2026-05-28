# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Relative Strength Index — Wilder's smoothing.

Numeric parity with vegas-core RSI.java. Wilder's RSI (the original 1978
formulation) seeds the average gain / loss as the simple mean over the
first ``period`` price diffs, then applies the modified smoothing

    avg = (prev_avg * (period - 1) + curr) / period

on every subsequent update. This is what TradingView ``ta.rsi``, Binance,
MT5, and most charting platforms emit by default — distinct from the
EMA-smoothed variants which produce a slightly more responsive curve.

Use cases:

* Mean-reversion oversold / overbought confirmation (e.g. Lyrid γ).
* Divergence detection (price higher high + RSI lower high → bearish).
* Regime filter (RSI persistently >50 on higher timeframe → uptrend).
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class RSI:
    """Wilder-smoothed RSI.

    Ready after exactly ``period`` price diffs have been observed
    (i.e. ``period + 1`` ``update()`` calls). ``get_value()`` returns
    ``0.0`` during warm-up; gate on :meth:`is_ready` before reading.

    Edge case: if the smoothed average loss is exactly zero (a strictly
    monotonic uptrend over the smoothing window) ``get_value()`` returns
    ``100.0``. Symmetric: average gain zero → ``0.0``.
    """

    def __init__(self, period: int = 14):
        if period < 2:
            raise ValueError(f"RSI period must be >= 2, got {period}")
        self.period = period
        self._prev_close: Optional[float] = None
        self._seed_gains: float = 0.0
        self._seed_losses: float = 0.0
        self._seed_count: int = 0
        self._avg_gain: float = 0.0
        self._avg_loss: float = 0.0
        self._initialized: bool = False

    def update(self, price: float) -> None:
        price = float(price)
        if self._prev_close is None:
            self._prev_close = price
            return
        change = price - self._prev_close
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        self._prev_close = price

        if not self._initialized:
            self._seed_gains += gain
            self._seed_losses += loss
            self._seed_count += 1
            if self._seed_count >= self.period:
                self._avg_gain = self._seed_gains / self.period
                self._avg_loss = self._seed_losses / self.period
                self._initialized = True
        else:
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period

    def get_value(self) -> float:
        if not self._initialized:
            return 0.0
        if self._avg_loss == 0.0:
            # Strictly monotonic uptrend over the window → RSI saturates.
            return 100.0 if self._avg_gain > 0.0 else 50.0
        rs = self._avg_gain / self._avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    def is_ready(self) -> bool:
        return self._initialized

    def get_period(self) -> int:
        return self.period

    def reset(self) -> None:
        self._prev_close = None
        self._seed_gains = 0.0
        self._seed_losses = 0.0
        self._seed_count = 0
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self._initialized = False

    def export_state(self) -> Dict[str, Any]:
        return {
            "prev_close": self._prev_close,
            "seed_gains": self._seed_gains,
            "seed_losses": self._seed_losses,
            "seed_count": self._seed_count,
            "avg_gain": self._avg_gain,
            "avg_loss": self._avg_loss,
            "initialized": self._initialized,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        pc = state["prev_close"]
        self._prev_close = float(pc) if pc is not None else None
        self._seed_gains = float(state["seed_gains"])
        self._seed_losses = float(state["seed_losses"])
        self._seed_count = int(state["seed_count"])
        self._avg_gain = float(state["avg_gain"])
        self._avg_loss = float(state["avg_loss"])
        self._initialized = bool(state["initialized"])
