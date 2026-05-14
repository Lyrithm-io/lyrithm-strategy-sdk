# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""SMA-seeded Exponential Moving Average. Numeric parity with vegas-core EMA.java."""
from __future__ import annotations

from typing import Any, Dict


class EMA:
    """SMA-seeded EMA. The first `period` values are averaged to seed the EMA;
    subsequent updates use the standard recursive form."""

    def __init__(self, period: int):
        if period < 1:
            raise ValueError(f"EMA period must be >= 1, got {period}")
        self.period = period
        self.multiplier = 2.0 / (period + 1)
        self.value = 0.0
        self.initialized = False
        self.count = 0
        self.sum = 0.0

    def update(self, price: float) -> None:
        if not self.initialized:
            self.sum += price
            self.count += 1
            if self.count >= self.period:
                self.value = self.sum / self.period
                self.initialized = True
        else:
            self.value = (price - self.value) * self.multiplier + self.value

    def get_value(self) -> float:
        return self.value if self.initialized else 0.0

    def is_ready(self) -> bool:
        return self.initialized

    def get_period(self) -> int:
        return self.period

    def reset(self) -> None:
        self.value = 0.0
        self.initialized = False
        self.count = 0
        self.sum = 0.0

    def export_state(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "initialized": self.initialized,
            "count": self.count,
            "sum": self.sum,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        self.value = float(state["value"])
        self.initialized = bool(state["initialized"])
        self.count = int(state["count"])
        self.sum = float(state["sum"])
