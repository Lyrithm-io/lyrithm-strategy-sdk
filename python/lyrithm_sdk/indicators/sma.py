# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Simple Moving Average — the entry-level moving-average indicator.

Numeric parity with vegas-core SMA.java. The first ``period`` updates fill
a fixed-size sliding window; from then on each new price displaces the
oldest one and the value re-averages over the window. Lighter than EMA
both in code and in trader intuition — the canonical first indicator a
new SDK user reaches for."""
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict


class SMA:
    """Fixed-window Simple Moving Average.

    Ready after exactly ``period`` updates; until then ``is_ready()`` is
    ``False`` and ``get_value()`` returns ``0.0``. Use this guard in
    strategy code to suppress signals during the warm-up window — see
    ``examples/sma-crossover/strategy.py``.
    """

    def __init__(self, period: int):
        if period < 1:
            raise ValueError(f"SMA period must be >= 1, got {period}")
        self.period = period
        # Bounded deque so the oldest sample is auto-evicted by Python.
        self._window: Deque[float] = deque(maxlen=period)
        self._sum: float = 0.0

    def update(self, price: float) -> None:
        if len(self._window) == self.period:
            # Window full — evicting the oldest by subtracting first
            # keeps the running sum exact (no float drift from re-summing).
            self._sum -= self._window[0]
        self._window.append(price)
        self._sum += price

    def get_value(self) -> float:
        if not self.is_ready():
            return 0.0
        return self._sum / self.period

    def is_ready(self) -> bool:
        return len(self._window) == self.period

    def get_period(self) -> int:
        return self.period

    def reset(self) -> None:
        self._window.clear()
        self._sum = 0.0

    def export_state(self) -> Dict[str, Any]:
        return {
            "window": list(self._window),
            "sum": self._sum,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        self._window.clear()
        for v in state["window"]:
            self._window.append(float(v))
        self._sum = float(state["sum"])
