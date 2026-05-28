# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Bollinger Bands — SMA midline with ±k·σ envelope.

Numeric parity with vegas-core BollingerBands.java (if/when ported). The
band is built on top of the bundled :class:`SMA`: middle = SMA(period),
upper/lower = middle ± multiplier · σ where σ is the **population**
standard deviation over the same window (the convention used by virtually
every charting platform: TradingView ``ta.bb``, Binance, MT5, etc.). Use
sample stdev (n−1 denominator) only if you have a specific reason.

Typical Bollinger-mean-reversion strategies tap the lower band on a long
entry and the upper band on a short; combined with an RSI oversold /
overbought confirmation and a trend filter this is the bread-and-butter
of the Lyrid γ (Sulafat) lineage.
"""
from __future__ import annotations

from collections import deque
from math import sqrt
from typing import Any, Deque, Dict


class BollingerBands:
    """Bollinger Bands with population-σ envelope.

    Ready after exactly ``period`` updates. ``get_middle()`` / ``get_upper()``
    / ``get_lower()`` all return ``0.0`` during warm-up; gate signals on
    :meth:`is_ready` instead.
    """

    def __init__(self, period: int, multiplier: float = 2.0):
        if period < 2:
            raise ValueError(f"BB period must be >= 2, got {period}")
        if multiplier <= 0:
            raise ValueError(f"BB multiplier must be > 0, got {multiplier}")
        self.period = period
        self.multiplier = float(multiplier)
        self._window: Deque[float] = deque(maxlen=period)

    def update(self, price: float) -> None:
        self._window.append(float(price))

    def get_middle(self) -> float:
        if not self.is_ready():
            return 0.0
        return sum(self._window) / self.period

    def get_stdev(self) -> float:
        if not self.is_ready():
            return 0.0
        mean = self.get_middle()
        var = sum((p - mean) ** 2 for p in self._window) / self.period
        return sqrt(var)

    def get_upper(self) -> float:
        if not self.is_ready():
            return 0.0
        return self.get_middle() + self.multiplier * self.get_stdev()

    def get_lower(self) -> float:
        if not self.is_ready():
            return 0.0
        return self.get_middle() - self.multiplier * self.get_stdev()

    def is_ready(self) -> bool:
        return len(self._window) == self.period

    def get_period(self) -> int:
        return self.period

    def get_multiplier(self) -> float:
        return self.multiplier

    def reset(self) -> None:
        self._window.clear()

    def export_state(self) -> Dict[str, Any]:
        return {"window": list(self._window)}

    def import_state(self, state: Dict[str, Any]) -> None:
        self._window.clear()
        for v in state["window"]:
            self._window.append(float(v))
