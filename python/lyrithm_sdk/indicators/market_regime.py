# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Market regime classifier: ADX level + ATR ratio + Bollinger Band width.

P4.1 (2026-06-05) — merged the sandbox-side additive directional mode so
authors can long/short gate via UPTREND / DOWNTREND labels without wiring
their own ADX. The dual-mode API stays back-compat with the strength-only
{STRONG_TREND / MODERATE_TREND / RANGE} contract — pass `adx_value` to
`update()` for the original behaviour, omit it to drive the internal ADX
and receive directional labels instead.
"""
from __future__ import annotations

import math
from collections import deque
from enum import Enum
from typing import Any, Dict

from .adx import ADX


class Regime(Enum):
    # Strength-only labels (returned when `update(candle, adx_value=...)` is called).
    STRONG_TREND = "STRONG_TREND"
    MODERATE_TREND = "MODERATE_TREND"
    # Directional labels (returned when `update(candle)` is called and the
    # internal ADX qualifies as a trend).
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    # Range labels (shared by both modes).
    LOW_VOLATILITY_RANGE = "LOW_VOLATILITY_RANGE"
    HIGH_VOLATILITY_RANGE = "HIGH_VOLATILITY_RANGE"


class MarketRegime:
    """ADX-driven trend classification, with ATR-ratio / BB-width tiebreakers
    for the ranging regimes. Matches vegas-core MarketRegime.java numerics
    in strength-only mode; directional mode is a P4.1 SDK addition.

    Two call modes (distinguished by whether `adx_value` is passed to `update`):

    1. **External ADX** — `update(candle, adx_value)`. Strength-only output
       (STRONG_TREND / MODERATE_TREND / RANGE). 1:1 backward-compat with
       vegas-adx and any other caller that runs its own ADX.

    2. **Self-contained** — `update(candle)`. Drives an internal ADX and
       returns *directional* labels (UPTREND / DOWNTREND / RANGE) so author
       strategies can long-vs-short gate without wiring ADX themselves.
    """

    ATR_HISTORY_PERIOD = 50

    def __init__(
        self,
        strong_trend_threshold: float = 40.0,
        moderate_trend_threshold: float = 25.0,
        atr_period: int = 14,
        bb_period: int = 20,
        bb_multiplier: float = 2.0,
        adx_period: int = 14,
        atr_history_period: int = ATR_HISTORY_PERIOD,
        atr_ratio_threshold: float = 1.3,
        bb_width_threshold: float = 6.0,
    ):
        if atr_history_period < 1:
            raise ValueError("ATR history period must be >= 1")
        self.strong_trend_threshold = strong_trend_threshold
        self.moderate_trend_threshold = moderate_trend_threshold
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.bb_multiplier = bb_multiplier
        self.atr_history_period = atr_history_period
        self.atr_ratio_threshold = atr_ratio_threshold
        self.bb_width_threshold = bb_width_threshold

        self.tr_values: deque = deque(maxlen=atr_period)
        self.close_prices: deque = deque(maxlen=bb_period)
        self.atr_history: deque = deque(maxlen=self.atr_history_period)

        self.atr = 0.0
        self.sma = 0.0
        self.bb_width = 0.0
        self.current_regime = Regime.LOW_VOLATILITY_RANGE
        self.ready = False
        self.count = 0
        self.prev_close = 0.0

        # Internal ADX powers the 1-arg directional mode. Drives every update
        # regardless of mode so state stays consistent if a caller switches.
        self._internal_adx = ADX(adx_period)

    def update(self, candle, adx_value: float | None = None) -> None:
        """Update regime with a new candle.

        Pass `adx_value` for strength-only classification (back-compat mode).
        Omit `adx_value` for self-contained directional classification.
        """
        high = candle.get("high") if isinstance(candle, dict) else candle.high
        low = candle.get("low") if isinstance(candle, dict) else candle.low
        close = candle.get("close") if isinstance(candle, dict) else candle.close

        self._internal_adx.update(candle)
        directional_mode = adx_value is None
        effective_adx = self._internal_adx.get_value() if directional_mode else adx_value

        self.count += 1

        if self.count == 1:
            tr = high - low
            self.prev_close = close
        else:
            tr = max(
                high - low,
                abs(high - self.prev_close),
                abs(low - self.prev_close),
            )
            self.prev_close = close

        self.tr_values.append(tr)
        if len(self.tr_values) >= self.atr_period:
            self.atr = sum(self.tr_values) / len(self.tr_values)
            self.atr_history.append(self.atr)

        self.close_prices.append(close)
        if len(self.close_prices) >= self.bb_period:
            self.sma = sum(self.close_prices) / len(self.close_prices)
            variance = sum((p - self.sma) ** 2 for p in self.close_prices) / len(
                self.close_prices
            )
            std_dev = math.sqrt(variance)
            upper = self.sma + (self.bb_multiplier * std_dev)
            lower = self.sma - (self.bb_multiplier * std_dev)
            self.bb_width = (upper - lower) / self.sma * 100.0 if self.sma > 0 else 0.0

        if self.count >= max(self.atr_period, self.bb_period):
            self.ready = True
            self.current_regime = self._classify_regime(
                effective_adx, directional=directional_mode
            )

    def _classify_regime(self, adx_value: float, *, directional: bool) -> Regime:
        if directional:
            # In directional mode any qualifying trend resolves to UPTREND or
            # DOWNTREND via +DI/-DI; otherwise fall through to the existing
            # volatility-range logic.
            if (
                adx_value >= self.moderate_trend_threshold
                and self._internal_adx.is_ready()
            ):
                plus_di = self._internal_adx.get_plus_di()
                minus_di = self._internal_adx.get_minus_di()
                return Regime.UPTREND if plus_di >= minus_di else Regime.DOWNTREND
        else:
            if adx_value >= self.strong_trend_threshold:
                return Regime.STRONG_TREND
            if adx_value >= self.moderate_trend_threshold:
                return Regime.MODERATE_TREND

        avg_atr = self._get_average_atr()
        atr_ratio = self.atr / avg_atr if avg_atr > 0 else 1.0
        if atr_ratio > self.atr_ratio_threshold or self.bb_width > self.bb_width_threshold:
            return Regime.HIGH_VOLATILITY_RANGE
        return Regime.LOW_VOLATILITY_RANGE

    def _get_average_atr(self) -> float:
        if not self.atr_history:
            return self.atr
        return sum(self.atr_history) / len(self.atr_history)

    def get_current_regime(self) -> Regime:
        return self.current_regime

    def get_regime(self) -> Regime:
        """Author-facing alias for get_current_regime()."""
        return self.current_regime

    def should_pause_trading(self) -> bool:
        return self.current_regime == Regime.HIGH_VOLATILITY_RANGE

    def is_ready(self) -> bool:
        return self.ready

    def get_atr(self) -> float:
        return self.atr

    def get_bb_width(self) -> float:
        return self.bb_width

    def get_atr_ratio(self) -> float:
        avg = self._get_average_atr()
        return self.atr / avg if avg > 0 else 1.0

    def reset(self) -> None:
        self.tr_values.clear()
        self.close_prices.clear()
        self.atr_history.clear()
        self.atr = 0.0
        self.sma = 0.0
        self.bb_width = 0.0
        self.current_regime = Regime.LOW_VOLATILITY_RANGE
        self.ready = False
        self.count = 0
        self.prev_close = 0.0
        self._internal_adx.reset()

    def export_state(self) -> Dict[str, Any]:
        return {
            "atr": self.atr,
            "sma": self.sma,
            "bbWidth": self.bb_width,
            "currentRegime": self.current_regime.name,
            "ready": self.ready,
            "count": self.count,
            "prevClose": self.prev_close,
            "trValues": list(self.tr_values),
            "closePrices": list(self.close_prices),
            "atrHistory": list(self.atr_history),
            "internalAdx": self._internal_adx.export_state(),
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        self.atr = float(state["atr"])
        self.sma = float(state["sma"])
        self.bb_width = float(state["bbWidth"])
        self.current_regime = Regime[state["currentRegime"]]
        self.ready = bool(state["ready"])
        self.count = int(state["count"])
        self.prev_close = float(state["prevClose"])

        self.tr_values.clear()
        for v in state.get("trValues", []) or []:
            self.tr_values.append(float(v))

        self.close_prices.clear()
        for v in state.get("closePrices", []) or []:
            self.close_prices.append(float(v))

        self.atr_history.clear()
        for v in state.get("atrHistory", []) or []:
            self.atr_history.append(float(v))

        internal = state.get("internalAdx")
        if internal:
            self._internal_adx.import_state(internal)
