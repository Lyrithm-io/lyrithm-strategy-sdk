# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Lyrid γ · Bollinger Mean-Reversion (Sulafat).

Open-source mean-reversion strategy in the Lyrid γ (Sulafat) lineage.
Sulafat sits at the parallelogram base of the constellation Lyra — the
steady-state anchor. γ rides the same theme: only trade when price is
oscillating around its long-term anchor, never when it's running.

----------------------------------------------------------------------
Logic — long-only mean reversion in a range-bound regime
----------------------------------------------------------------------

Long entry fires when ALL four conditions hold on a closed candle:

  1. Touch  : ``low <= BB_lower`` — price has tagged the lower envelope
  2. Stretch: ``RSI(14) < rsi_oversold`` — momentum is oversold
  3. Trend  : ``close > EMA(long) * trend_buffer`` — still above the
              long-trend floor (kills entries in obvious downtrends)
  4. Regime : ``|close - EMA(long)| / EMA(long) < range_band_pct`` —
              price is oscillating around the anchor, not breaking out

Short side is intentionally disabled (``check_short_entry`` always
returns 0) because the strategy is asymmetric: BTC and most majors have
a long-term positive drift, so chasing the upper-band-tag-short symmetry
is a known under-performer over long backtests. Fork the file if you
want the symmetric variant.

----------------------------------------------------------------------
Risk model
----------------------------------------------------------------------

Stop-loss = ``entry × (1 - stop_loss_pct)``
Take-profit = stop × ``get_dynamic_reward_ratio()`` (computed below as
``take_profit_pct / stop_loss_pct`` so the configured TP/SL pair just
work — defaults give R:R = 2.0).

Leverage and reward ratio are tunable. Position size comes from the
platform's sizer (percent-of-equity by default), so the strategy itself
stays size-agnostic.

----------------------------------------------------------------------
Defaults
----------------------------------------------------------------------

  bb_length          20      (lookback for BB and the EMA-trend filter)
  bb_stdev           2.0     (BB envelope width, σ multiplier)
  rsi_oversold       40      (RSI buy threshold)
  ema_length         100     (long anchor)
  trend_buffer       0.95    (close > EMA × this; 0.95 = 5% slack)
  range_band_pct     0.08    (8% — width of the "ranging" regime)
  stop_loss_pct      0.025   (2.5%)
  take_profit_pct    0.05    (5%  — R:R = 2.0)
  leverage           5

All values match the original Pine source the strategy was ported from.
"""
from __future__ import annotations

from typing import Any, Mapping

from lyrithm_sdk import Candle, Strategy
from lyrithm_sdk.indicators import RSI, BollingerBands, EMA


class GammaBollingerMeanReversion(Strategy):
    def __init__(self, config: Mapping[str, Any]):
        self.bb = BollingerBands(
            period=int(config.get("bb_length", 20)),
            multiplier=float(config.get("bb_stdev", 2.0)),
        )
        self.rsi = RSI(int(config.get("rsi_period", 14)))
        self.ema = EMA(int(config.get("ema_length", 100)))

        self.rsi_oversold = float(config.get("rsi_oversold", 40))
        self.trend_buffer = float(config.get("trend_buffer", 0.95))
        self.range_band_pct = float(config.get("range_band_pct", 0.08))
        self.stop_loss_pct = float(config.get("stop_loss_pct", 0.025))
        self.take_profit_pct = float(config.get("take_profit_pct", 0.05))
        self.leverage = int(config.get("leverage", 5))

        self._last: Candle | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def update(self, candle: Candle) -> None:
        self.bb.update(candle.close)
        self.rsi.update(candle.close)
        self.ema.update(candle.close)
        self._last = candle

    def is_ready(self) -> bool:
        return self.bb.is_ready() and self.rsi.is_ready() and self.ema.is_ready()

    def reset(self) -> None:
        self.bb.reset()
        self.rsi.reset()
        self.ema.reset()
        self._last = None

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def check_long_entry(self) -> int:
        if self._last is None:
            return 0
        c = self._last.close
        l = self._last.low
        ema_v = self.ema.get_value()
        if ema_v == 0.0:
            return 0
        in_range = abs(c - ema_v) / ema_v < self.range_band_pct
        touched_lower = l <= self.bb.get_lower()
        oversold = self.rsi.get_value() < self.rsi_oversold
        above_trend_floor = c > ema_v * self.trend_buffer
        if touched_lower and oversold and above_trend_floor and in_range:
            return 1  # rule 1: BB-lower mean-reversion long
        return 0

    def check_short_entry(self) -> int:
        # Long-only by design — fork the file to enable upper-band shorts.
        return 0

    # ------------------------------------------------------------------
    # Risk
    # ------------------------------------------------------------------

    def calculate_long_stop_loss(self) -> float:
        assert self._last is not None
        return self._last.close * (1.0 - self.stop_loss_pct)

    def calculate_short_stop_loss(self) -> float:
        # Never called (check_short_entry returns 0). Returns a safe far-
        # away placeholder so a misconfigured caller never hits a 0 stop.
        assert self._last is not None
        return self._last.close * (1.0 + self.stop_loss_pct)

    def get_dynamic_reward_ratio(self) -> float:
        # TP-pct / SL-pct so user's two knobs drive the R:R coherently.
        if self.stop_loss_pct <= 0:
            return 1.0
        return self.take_profit_pct / self.stop_loss_pct

    def get_dynamic_leverage(self) -> int:
        return self.leverage


def create_strategy(config: Mapping[str, Any]) -> Strategy:
    return GammaBollingerMeanReversion(config or {})
