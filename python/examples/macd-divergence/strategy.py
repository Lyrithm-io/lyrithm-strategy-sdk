# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""MACD histogram divergence — classic momentum-leads-price reversal signal.

Detects the two textbook divergence patterns by comparing the most
recent price extreme against the histogram value at the same bar:

* **Bullish (long entry)** — current close prints a new low over the
  ``divergence_lookback`` window, AND the current histogram value is
  STRICTLY HIGHER than the histogram value at the prior low within the
  window. Price extended further down, momentum didn't follow.
* **Bearish (short entry)** — current close prints a new high over the
  window, AND the current histogram is STRICTLY LOWER than the
  histogram at the prior high. Price extended further up, momentum
  capitulated.

Notes on the simplification: the spec for P4.2 mentions "MTF confirm",
but the SDK's single-stream Strategy contract doesn't expose
``request.security()`` / multi-timeframe primitives, so the strategy
ships with a single-timeframe divergence rule. Authors who want HTF
confirm can extend the class with a second instance fed by an
external aggregator.

The MACD itself is computed inline from two EMAs + a signal EMA —
keeps this file self-contained at the cost of duplicating ~12 lines
of well-known math.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from lyrithm_sdk import Candle, Strategy
from lyrithm_sdk.indicators import ATR, EMA


# Minimum candles before any signal can fire — guards a fresh boot from
# emitting a spurious divergence on partial state.
_MIN_WARMUP_BARS = 4


class MacdDivergence(Strategy):
    def __init__(self, config: Mapping[str, Any]):
        fast = int(config.get("macd_fast", 12))
        slow = int(config.get("macd_slow", 26))
        signal = int(config.get("macd_signal", 9))
        if fast >= slow:
            raise ValueError(
                f"macd_fast ({fast}) must be < macd_slow ({slow})"
            )

        self.ema_fast = EMA(fast)
        self.ema_slow = EMA(slow)
        self.ema_signal = EMA(signal)
        self.atr = ATR(int(config.get("atr_period", 14)))

        self.divergence_lookback = max(4, int(config.get("divergence_lookback", 20)))
        self.stop_atr_mult = float(config.get("stop_atr_mult", 2.0))
        self.reward_ratio = float(config.get("reward_ratio", 2.5))
        self.leverage = int(config.get("leverage", 3))

        # Per-bar history of (close, histogram). Bounded so the rolling
        # window stays cheap to scan.
        self._closes: deque[float] = deque(maxlen=self.divergence_lookback)
        self._histograms: deque[float] = deque(maxlen=self.divergence_lookback)
        self._last: Candle | None = None
        self._bars_seen = 0
        self._signal_initialised = False

    def update(self, candle: Candle) -> None:
        self.ema_fast.update(candle.close)
        self.ema_slow.update(candle.close)
        self.atr.update(candle)

        # Compute MACD only once both base EMAs are warm so the signal
        # line doesn't seed against transient zero values.
        if self.ema_fast.is_ready() and self.ema_slow.is_ready():
            macd_line = self.ema_fast.get_value() - self.ema_slow.get_value()
            self.ema_signal.update(macd_line)
            if self.ema_signal.is_ready():
                self._signal_initialised = True
                histogram = macd_line - self.ema_signal.get_value()
                self._closes.append(candle.close)
                self._histograms.append(histogram)

        self._last = candle
        self._bars_seen += 1

    def is_ready(self) -> bool:
        return (
            self._bars_seen >= _MIN_WARMUP_BARS
            and self._signal_initialised
            and self.atr.is_ready()
            and len(self._closes) == self.divergence_lookback
        )

    def check_long_entry(self) -> int:
        if not self.is_ready():
            return 0
        closes = list(self._closes)
        hists = list(self._histograms)
        curr_close = closes[-1]
        curr_hist = hists[-1]
        # Current close is a new low over the window (vs every prior point).
        if any(c <= curr_close for c in closes[:-1]):
            return 0
        # Prior low = the minimum close among the rest of the window.
        prior_low_idx = min(range(len(closes) - 1), key=lambda i: closes[i])
        prior_low_hist = hists[prior_low_idx]
        # Bullish divergence: price made lower low, histogram printed
        # higher low (momentum didn't confirm the price extreme).
        return 1 if curr_hist > prior_low_hist else 0

    def check_short_entry(self) -> int:
        if not self.is_ready():
            return 0
        closes = list(self._closes)
        hists = list(self._histograms)
        curr_close = closes[-1]
        curr_hist = hists[-1]
        if any(c >= curr_close for c in closes[:-1]):
            return 0
        prior_high_idx = max(range(len(closes) - 1), key=lambda i: closes[i])
        prior_high_hist = hists[prior_high_idx]
        return 1 if curr_hist < prior_high_hist else 0

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
        self.ema_signal.reset()
        self.atr.reset()
        self._closes.clear()
        self._histograms.clear()
        self._last = None
        self._bars_seen = 0
        self._signal_initialised = False


def create_strategy(config: Mapping[str, Any]) -> Strategy:
    return MacdDivergence(config or {})
