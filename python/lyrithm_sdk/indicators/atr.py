# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Average True Range (Wilder's smoothing). Common stop-loss / volatility primitive.

P4.1 (2026-06-05) — merged the sandbox-side `_has_prev` first-candle skip
semantics so the SDK matches the production sandbox port 1:1. The first
update now anchors prev_close without producing a TR (which is the
textbook Wilder formulation: TR requires a previous close to compute
the close-to-close range). Net effect: warmup is one candle longer
than the previous SDK version — `is_ready()` flips after `period + 1`
total updates instead of `period`. `import_state()` keeps a back-compat
branch for the old `{value, seedWindow}` shape so persisted state from
the pre-merge SDK still loads.
"""
from __future__ import annotations

from typing import Any, Dict


class ATR:
    """Wilder-smoothed Average True Range.

    Anchors prev_close on the first update, then seeds with the arithmetic
    mean of the next `period` true ranges, then advances via the standard
    Wilder recursion: ATR_n = ATR_{n-1} - (ATR_{n-1} / period) + TR_n / period.
    """

    def __init__(self, period: int = 14):
        if period < 1:
            raise ValueError(f"ATR period must be >= 1, got {period}")
        self.period = period
        self.alpha = 1.0 / period
        self.initialized = False
        self.count = 0

        self.prev_close = 0.0
        self.tr_sum = 0.0
        self.atr = 0.0
        self._has_prev = False

    def update(self, candle) -> None:
        """Update ATR with a new candle (Candle dataclass or dict)."""
        high = candle.get("high") if isinstance(candle, dict) else candle.high
        low = candle.get("low") if isinstance(candle, dict) else candle.low
        close = candle.get("close") if isinstance(candle, dict) else candle.close

        if not self._has_prev:
            self.prev_close = close
            self._has_prev = True
            return

        current_tr = max(
            high - low,
            abs(high - self.prev_close),
            abs(low - self.prev_close),
        )

        self.count += 1
        if self.count < self.period:
            self.tr_sum += current_tr
        elif self.count == self.period:
            self.tr_sum += current_tr
            self.atr = self.tr_sum / self.period
            self.initialized = True
        else:
            self.atr = self.atr - self.atr * self.alpha + current_tr * self.alpha

        self.prev_close = close

    def get_value(self) -> float:
        return self.atr if self.initialized else 0.0

    def is_ready(self) -> bool:
        return self.initialized

    def get_period(self) -> int:
        return self.period

    def reset(self) -> None:
        self.initialized = False
        self.count = 0
        self.prev_close = 0.0
        self.tr_sum = 0.0
        self.atr = 0.0
        self._has_prev = False

    def export_state(self) -> Dict[str, Any]:
        return {
            "prevClose": self.prev_close,
            "trSum": self.tr_sum,
            "atr": self.atr,
            "initialized": self.initialized,
            "count": self.count,
            "hasPrev": self._has_prev,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        # Back-compat: the pre-P4.1 SDK exported {value, seedWindow, ...}.
        # Recognise it by the presence of "value" and translate to the new
        # field layout so an upgrade doesn't drop in-flight strategies'
        # warmup state.
        if "value" in state and "atr" not in state:
            self.atr = float(state["value"])
            self.initialized = bool(state["initialized"])
            self.count = int(state["count"])
            self.prev_close = float(state["prevClose"])
            self.tr_sum = float(sum(state.get("seedWindow", []) or []))
            # The old shape didn't track hasPrev — if count > 0 we know
            # at least one update has landed, so prev_close is anchored.
            self._has_prev = self.count > 0
            return

        self.prev_close = float(state["prevClose"])
        self.tr_sum = float(state["trSum"])
        self.atr = float(state["atr"])
        self.initialized = bool(state["initialized"])
        self.count = int(state["count"])
        self._has_prev = bool(state.get("hasPrev", state["count"] > 0))
