# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Minimal EMA-cross strategy — the smallest viable Lyrithm strategy.

Read this first when learning the SDK; it touches every required method on
the Strategy ABC without any extras."""
from __future__ import annotations

from typing import Any, Mapping

from lyrithm_sdk import Candle, Strategy
from lyrithm_sdk.indicators import ATR, EMA


class EmaCross(Strategy):
    def __init__(self, config: Mapping[str, Any]):
        self.ema_fast = EMA(int(config.get("ema_fast", 12)))
        self.ema_slow = EMA(int(config.get("ema_slow", 26)))
        self.atr = ATR(14)
        self.stop_atr_mult = float(config.get("stop_atr_mult", 1.5))
        self.reward_ratio = float(config.get("reward_ratio", 2.0))
        self.leverage = int(config.get("leverage", 5))
        self._prev_diff: float | None = None
        self._last: Candle | None = None

    def update(self, candle: Candle) -> None:
        self.ema_fast.update(candle.close)
        self.ema_slow.update(candle.close)
        self.atr.update(candle)
        self._last = candle

    def is_ready(self) -> bool:
        return self.ema_fast.is_ready() and self.ema_slow.is_ready() and self.atr.is_ready()

    def check_long_entry(self) -> int:
        diff = self.ema_fast.get_value() - self.ema_slow.get_value()
        fired = self._prev_diff is not None and self._prev_diff <= 0 < diff
        self._prev_diff = diff
        return 1 if fired else 0

    def check_short_entry(self) -> int:
        diff = self.ema_fast.get_value() - self.ema_slow.get_value()
        fired = self._prev_diff is not None and self._prev_diff >= 0 > diff
        return 1 if fired else 0

    def calculate_long_stop_loss(self) -> float:
        assert self._last is not None
        return self._last.close - self.atr.get_value() * self.stop_atr_mult

    def calculate_short_stop_loss(self) -> float:
        assert self._last is not None
        return self._last.close + self.atr.get_value() * self.stop_atr_mult

    def get_dynamic_reward_ratio(self) -> float:
        return self.reward_ratio

    def get_dynamic_leverage(self) -> int:
        return self.leverage

    def reset(self) -> None:
        self.ema_fast.reset()
        self.ema_slow.reset()
        self.atr.reset()
        self._prev_diff = None
        self._last = None


def create_strategy(config: Mapping[str, Any]) -> Strategy:
    return EmaCross(config or {})
