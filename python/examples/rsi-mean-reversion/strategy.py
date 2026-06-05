# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""RSI mean-reversion — buy oversold bounces, sell overbought rejections.

A classic "fade the extreme" strategy. Sits at the opposite end of the
spectrum from ``sma-crossover`` (pure trend-following) so a buyer can
A/B the two flavours on the same instrument without writing any code.

Logic:

* RSI(14) by default; configurable.
* Long entry when RSI crosses BACK ABOVE ``oversold_threshold`` after
  printing a sub-oversold value last bar. We require the *cross-back*
  rather than the bare extreme so a freefalling market doesn't catch
  a knife at RSI 18 only to keep dropping to RSI 8.
* Short entry symmetrically when RSI crosses BACK BELOW
  ``overbought_threshold`` after printing an overbought value last bar.
* ATR stop = entry ± ``stop_atr_mult * ATR(14)``.
* Reward ratio + leverage defaults reflect the mean-revert thesis
  (tighter reward target than trend strategies; cap leverage at 3x).

Compare with ``examples/sma-crossover`` (trend) and ``examples/donchian-breakout``
(volatility breakout) for a balanced 3-way fork starter pack.
"""
from __future__ import annotations

from typing import Any, Mapping

from lyrithm_sdk import Candle, Strategy
from lyrithm_sdk.indicators import ATR, RSI


# Minimum candles before any signal can fire — guards against a freshly
# constructed indicator emitting a spurious cross on the very first bar.
_MIN_WARMUP_BARS = 4


class RsiMeanReversion(Strategy):
    def __init__(self, config: Mapping[str, Any]):
        self.rsi = RSI(int(config.get("rsi_period", 14)))
        self.atr = ATR(int(config.get("atr_period", 14)))
        self.oversold_threshold = float(config.get("oversold_threshold", 30.0))
        self.overbought_threshold = float(config.get("overbought_threshold", 70.0))
        self.stop_atr_mult = float(config.get("stop_atr_mult", 2.0))
        self.reward_ratio = float(config.get("reward_ratio", 1.5))
        self.leverage = int(config.get("leverage", 3))
        # Track previous RSI so we can detect cross-back events frame-by-frame.
        self._prev_rsi: float | None = None
        self._bars_seen = 0
        self._last: Candle | None = None

    def update(self, candle: Candle) -> None:
        self.rsi.update(candle.close)
        self.atr.update(candle)
        self._last = candle
        self._bars_seen += 1

    def is_ready(self) -> bool:
        return (
            self._bars_seen >= _MIN_WARMUP_BARS
            and self.rsi.is_ready()
            and self.atr.is_ready()
        )

    def check_long_entry(self) -> int:
        curr = self.rsi.get_value()
        fired = (
            self._prev_rsi is not None
            and self._prev_rsi < self.oversold_threshold
            and curr >= self.oversold_threshold
        )
        self._prev_rsi = curr
        return 1 if fired else 0

    def check_short_entry(self) -> int:
        # Long-side check ran first this tick and already advanced
        # ``_prev_rsi``, so short-side observes the same prev → curr
        # transition without double-stepping.
        curr = self.rsi.get_value()
        fired = (
            self._prev_rsi is not None
            and self._prev_rsi > self.overbought_threshold
            and curr <= self.overbought_threshold
        )
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
        self.rsi.reset()
        self.atr.reset()
        self._prev_rsi = None
        self._bars_seen = 0
        self._last = None


def create_strategy(config: Mapping[str, Any]) -> Strategy:
    return RsiMeanReversion(config or {})
