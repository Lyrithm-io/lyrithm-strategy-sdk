# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Average True Range (Wilder's smoothing). Common stop-loss / volatility primitive."""
from __future__ import annotations

from collections import deque
from typing import Any, Dict


class ATR:
    """Wilder's ATR. The first `period` true ranges are averaged to seed, then
    smoothed recursively: ATR_t = ATR_{t-1} * (1 - 1/N) + TR_t * (1/N)."""

    def __init__(self, period: int = 14):
        if period < 1:
            raise ValueError(f"ATR period must be >= 1, got {period}")
        self.period = period
        self.alpha = 1.0 / period
        self.value = 0.0
        self.initialized = False
        self.count = 0
        self.prev_close = 0.0
        self.seed_window: deque = deque(maxlen=period)

    def update(self, candle) -> None:
        high = candle.get("high") if isinstance(candle, dict) else candle.high
        low = candle.get("low") if isinstance(candle, dict) else candle.low
        close = candle.get("close") if isinstance(candle, dict) else candle.close

        if self.count == 0:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))

        if not self.initialized:
            self.seed_window.append(tr)
            if len(self.seed_window) >= self.period:
                self.value = sum(self.seed_window) / self.period
                self.initialized = True
        else:
            self.value = self.value - (self.value * self.alpha) + tr * self.alpha

        self.prev_close = close
        self.count += 1

    def get_value(self) -> float:
        return self.value if self.initialized else 0.0

    def is_ready(self) -> bool:
        return self.initialized

    def reset(self) -> None:
        self.value = 0.0
        self.initialized = False
        self.count = 0
        self.prev_close = 0.0
        self.seed_window.clear()

    def export_state(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "initialized": self.initialized,
            "count": self.count,
            "prevClose": self.prev_close,
            "seedWindow": list(self.seed_window),
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        self.value = float(state["value"])
        self.initialized = bool(state["initialized"])
        self.count = int(state["count"])
        self.prev_close = float(state["prevClose"])
        self.seed_window.clear()
        for v in state.get("seedWindow", []) or []:
            self.seed_window.append(float(v))
