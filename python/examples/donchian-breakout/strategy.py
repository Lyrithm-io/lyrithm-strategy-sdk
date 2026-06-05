# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Donchian channel breakout — Turtle-style high/low breakout with trailing stop.

The classic Richard Dennis "Turtle" entry signal applied to crypto futures:

* Long when the latest candle closes ABOVE the highest high of the prior
  ``channel_period`` candles (default 20).
* Short when the latest candle closes BELOW the lowest low of the prior
  ``channel_period`` candles.
* Stop-loss rides the opposite-side Donchian boundary, trailed wider by
  ``stop_atr_mult * ATR(14)`` so a single bad bar doesn't immediately
  flip the trade.
* Sensible reward ratio (3.0 — breakouts are momentum trades that want
  room to run) and modest 5x leverage.

This rounds out the bundled triad alongside ``sma-crossover``
(trend MA) and ``rsi-mean-reversion`` (fade) so a buyer's first
exposure to authoring covers the three canonical strategy families.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from lyrithm_sdk import Candle, Strategy
from lyrithm_sdk.indicators import ATR


# Minimum candles before any signal can fire — guards a fresh boot from
# emitting a spurious breakout on the very first bar.
_MIN_WARMUP_BARS = 4


class DonchianBreakout(Strategy):
    def __init__(self, config: Mapping[str, Any]):
        self.channel_period = max(2, int(config.get("channel_period", 20)))
        self.atr = ATR(int(config.get("atr_period", 14)))
        self.stop_atr_mult = float(config.get("stop_atr_mult", 1.5))
        self.reward_ratio = float(config.get("reward_ratio", 3.0))
        self.leverage = int(config.get("leverage", 5))
        # PRIOR channel: highs/lows from the N candles BEFORE the
        # current bar. We exclude the current bar from the comparison
        # so "close above prior high" is computed cleanly.
        self._prior_highs: deque[float] = deque(maxlen=self.channel_period)
        self._prior_lows: deque[float] = deque(maxlen=self.channel_period)
        self._last: Candle | None = None
        self._bars_seen = 0

    def update(self, candle: Candle) -> None:
        # Push the PREVIOUS candle into the prior buffer before swapping
        # in the new one — that way `_prior_highs` / `_prior_lows` always
        # describe the N candles before `self._last`, never including
        # the current bar.
        if self._last is not None:
            self._prior_highs.append(self._last.high)
            self._prior_lows.append(self._last.low)
        self.atr.update(candle)
        self._last = candle
        self._bars_seen += 1

    def is_ready(self) -> bool:
        return (
            self._bars_seen >= _MIN_WARMUP_BARS
            and len(self._prior_highs) >= self.channel_period
            and self.atr.is_ready()
        )

    def _highest_prior_high(self) -> float:
        return max(self._prior_highs)

    def _lowest_prior_low(self) -> float:
        return min(self._prior_lows)

    def check_long_entry(self) -> int:
        if self._last is None or not self.is_ready():
            return 0
        return 1 if self._last.close > self._highest_prior_high() else 0

    def check_short_entry(self) -> int:
        if self._last is None or not self.is_ready():
            return 0
        return 1 if self._last.close < self._lowest_prior_low() else 0

    def calculate_long_stop_loss(self) -> float:
        assert self._last is not None
        # Stop sits at the lower band, trailed wider by ATR.
        if not self._prior_lows:
            return self._last.close - self.atr.get_value() * self.stop_atr_mult
        return self._lowest_prior_low() - self.atr.get_value() * self.stop_atr_mult

    def calculate_short_stop_loss(self) -> float:
        assert self._last is not None
        if not self._prior_highs:
            return self._last.close + self.atr.get_value() * self.stop_atr_mult
        return self._highest_prior_high() + self.atr.get_value() * self.stop_atr_mult

    def get_dynamic_reward_ratio(self) -> float:
        return self.reward_ratio

    def get_dynamic_leverage(self) -> int:
        return self.leverage

    def reset(self) -> None:
        self.atr.reset()
        self._prior_highs.clear()
        self._prior_lows.clear()
        self._last = None
        self._bars_seen = 0


def create_strategy(config: Mapping[str, Any]) -> Strategy:
    return DonchianBreakout(config or {})
