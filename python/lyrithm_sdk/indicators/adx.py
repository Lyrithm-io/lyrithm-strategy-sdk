# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Wilder's ADX with +DI/-DI and slope detection. Numeric parity with ADX.java."""
from __future__ import annotations

from collections import deque
from typing import Any, Dict


class ADX:
    """Wilder's ADX with +DI, -DI, and slope detection."""

    SLOPE_LOOKBACK = 5

    def __init__(self, period: int):
        if period < 2:
            raise ValueError(f"ADX period must be >= 2, got {period}")
        self.period = period
        self.alpha = 1.0 / period
        self.initialized = False
        self.count = 0

        self.prev_high = 0.0
        self.prev_low = 0.0
        self.prev_close = 0.0

        self.tr = 0.0
        self.plus_dm = 0.0
        self.minus_dm = 0.0
        self.plus_di = 0.0
        self.minus_di = 0.0
        self.dx = 0.0
        self.adx = 0.0

        self.adx_history: deque = deque(maxlen=self.SLOPE_LOOKBACK + 1)

    def update(self, candle) -> None:
        """Feed one candle. Accepts a Candle dataclass or a dict with
        'high'/'low'/'close' keys."""
        high = candle.get("high") if isinstance(candle, dict) else candle.high
        low = candle.get("low") if isinstance(candle, dict) else candle.low
        close = candle.get("close") if isinstance(candle, dict) else candle.close

        if self.count == 0:
            self.prev_high = high
            self.prev_low = low
            self.prev_close = close
            self.count += 1
            return

        current_tr = max(
            high - low,
            abs(high - self.prev_close),
            abs(low - self.prev_close),
        )

        up_move = high - self.prev_high
        down_move = self.prev_low - low

        current_plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
        current_minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

        if self.count < self.period:
            self.tr = (self.tr * (self.count - 1) + current_tr) / self.count
            self.plus_dm = (self.plus_dm * (self.count - 1) + current_plus_dm) / self.count
            self.minus_dm = (self.minus_dm * (self.count - 1) + current_minus_dm) / self.count
        else:
            self.tr = self.tr - (self.tr * self.alpha) + current_tr * self.alpha
            self.plus_dm = self.plus_dm - (self.plus_dm * self.alpha) + current_plus_dm * self.alpha
            self.minus_dm = self.minus_dm - (self.minus_dm * self.alpha) + current_minus_dm * self.alpha

            if self.tr > 0:
                self.plus_di = 100.0 * (self.plus_dm / self.tr)
                self.minus_di = 100.0 * (self.minus_dm / self.tr)
                di_sum = self.plus_di + self.minus_di
                if di_sum > 0:
                    self.dx = 100.0 * abs(self.plus_di - self.minus_di) / di_sum
                    if not self.initialized:
                        self.adx = self.dx
                        self.initialized = True
                    else:
                        self.adx = self.adx - (self.adx * self.alpha) + self.dx * self.alpha
                    self.adx_history.append(self.adx)

        self.prev_high = high
        self.prev_low = low
        self.prev_close = close
        self.count += 1

    def get_value(self) -> float:
        return self.adx if self.initialized else 0.0

    def get_plus_di(self) -> float:
        return self.plus_di if self.initialized else 0.0

    def get_minus_di(self) -> float:
        return self.minus_di if self.initialized else 0.0

    def is_ready(self) -> bool:
        return self.initialized

    def get_period(self) -> int:
        return self.period

    def get_slope(self) -> float:
        if len(self.adx_history) < 2:
            return 0.0
        h = list(self.adx_history)
        return (h[-1] - h[0]) / (len(h) - 1)

    def is_slope_up(self) -> bool:
        return self.get_slope() > 0

    def reset(self) -> None:
        self.adx_history.clear()
        self.initialized = False
        self.count = 0
        self.tr = 0.0
        self.plus_dm = 0.0
        self.minus_dm = 0.0
        self.plus_di = 0.0
        self.minus_di = 0.0
        self.dx = 0.0
        self.adx = 0.0
        self.prev_high = 0.0
        self.prev_low = 0.0
        self.prev_close = 0.0

    def export_state(self) -> Dict[str, Any]:
        return {
            "prevHigh": self.prev_high,
            "prevLow": self.prev_low,
            "prevClose": self.prev_close,
            "tr": self.tr,
            "plusDM": self.plus_dm,
            "minusDM": self.minus_dm,
            "plusDI": self.plus_di,
            "minusDI": self.minus_di,
            "dx": self.dx,
            "adx": self.adx,
            "initialized": self.initialized,
            "count": self.count,
            "adxHistory": list(self.adx_history),
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        self.prev_high = float(state["prevHigh"])
        self.prev_low = float(state["prevLow"])
        self.prev_close = float(state["prevClose"])
        self.tr = float(state["tr"])
        self.plus_dm = float(state["plusDM"])
        self.minus_dm = float(state["minusDM"])
        self.plus_di = float(state["plusDI"])
        self.minus_di = float(state["minusDI"])
        self.dx = float(state["dx"])
        self.adx = float(state["adx"])
        self.initialized = bool(state["initialized"])
        self.count = int(state["count"])
        self.adx_history.clear()
        for v in state.get("adxHistory", []) or []:
            self.adx_history.append(float(v))
