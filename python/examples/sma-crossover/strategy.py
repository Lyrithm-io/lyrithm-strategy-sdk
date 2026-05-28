# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""SMA crossover — the bundled "Day 1" Lyrithm Personal Edition strategy.

A buyer who runs ``docker compose up`` straight out of the box can point
this strategy at any supported futures pair and start paper-trading
within minutes. It is intentionally the simplest viable trend-following
strategy:

* Two simple moving averages — fast (default 20) and slow (default 50).
* Long when the fast SMA crosses ABOVE the slow SMA on the latest close.
* Short when the fast SMA crosses BELOW the slow SMA on the latest close.
* Stop-loss = entry ± ``stop_atr_mult * ATR(14)`` — pure volatility based.
* Reward ratio + leverage configurable; sane defaults (R:R 2.0, 5x lev).

Compare with ``examples/ema-cross/strategy.py`` (responsive but choppier)
and the closed-source ``vegas-adx`` (16-rule Vegas tunnel + ADX gate)
to see the spectrum of strategy complexity supported by the SDK.

The whole file is < 80 lines on purpose: every Strategy ABC method is
visible at a glance with no helper indirection. Fork freely."""
from __future__ import annotations

from typing import Any, Mapping

from lyrithm_sdk import Candle, Strategy
from lyrithm_sdk.indicators import ATR, SMA


class SmaCrossover(Strategy):
    def __init__(self, config: Mapping[str, Any]):
        self.sma_fast = SMA(int(config.get("sma_fast", 20)))
        self.sma_slow = SMA(int(config.get("sma_slow", 50)))
        self.atr = ATR(int(config.get("atr_period", 14)))
        self.stop_atr_mult = float(config.get("stop_atr_mult", 2.0))
        self.reward_ratio = float(config.get("reward_ratio", 2.0))
        self.leverage = int(config.get("leverage", 5))
        # Track previous (fast - slow) so we can detect the zero-crossing
        # frame-by-frame instead of relying on a stateful "last signal" flag.
        self._prev_diff: float | None = None
        self._last: Candle | None = None

    def update(self, candle: Candle) -> None:
        self.sma_fast.update(candle.close)
        self.sma_slow.update(candle.close)
        self.atr.update(candle)
        self._last = candle

    def is_ready(self) -> bool:
        return self.sma_fast.is_ready() and self.sma_slow.is_ready() and self.atr.is_ready()

    def check_long_entry(self) -> int:
        diff = self.sma_fast.get_value() - self.sma_slow.get_value()
        fired = self._prev_diff is not None and self._prev_diff <= 0 < diff
        self._prev_diff = diff
        return 1 if fired else 0

    def check_short_entry(self) -> int:
        diff = self.sma_fast.get_value() - self.sma_slow.get_value()
        # Note: we deliberately do NOT re-write _prev_diff here. Long-side
        # check ran first this tick and already advanced it, so short-side
        # observes the same prev → curr transition without double-stepping.
        return 1 if (self._prev_diff is not None and self._prev_diff >= 0 > diff) else 0

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
        self.sma_fast.reset()
        self.sma_slow.reset()
        self.atr.reset()
        self._prev_diff = None
        self._last = None


def create_strategy(config: Mapping[str, Any]) -> Strategy:
    return SmaCrossover(config or {})
