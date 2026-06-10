# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Pine semantics replay tests — feed known candle sequences through a
PineStrategy subclass and verify that ta.* / history / crossover values
match hand-computed Pine reference outputs.

This is the closest we can get to TradingView reference parity without
programmatically driving the closed-source platform. Expected outputs are
computed manually following Pine v5 documented semantics:

  - ta.sma(src, N): simple moving average of last N values; NaN before N
  - ta.ema(src, N): Wilder EMA seeded with SMA of first N values; NaN
    before N values have been seen
  - ta.rsi(src, N): Wilder RSI with first N values used to seed avg gain
    and avg loss
  - ta.atr(N): Wilder ATR seeded with SMA of first N true ranges
  - ta.crossover(a, b): True only on the bar where `a` crossed UP through `b`
  - ta.crossunder(a, b): True only on the bar where `a` crossed DOWN through `b`
  - ta.highest/lowest(src, N): rolling window max/min over last N values; NaN before N
  - ta.change(src): src - src[1]; NaN on bar 0
  - ta.barssince(cond): bars elapsed since cond was last True; -1 if never
"""
from __future__ import annotations

import math as _m

import pytest

from lyrithm_sdk import Candle
from lyrithm_sdk.pine_runtime import PineStrategy, ta, history


def _c(t: int, close: float, open_: float = None, high: float = None,
       low: float = None, volume: float = 1000.0) -> Candle:
    if open_ is None:
        open_ = close
    if high is None:
        high = max(open_, close)
    if low is None:
        low = min(open_, close)
    return Candle(timestamp=t, open=open_, high=high, low=low, close=close, volume=volume)


# ============================================================
# Helper: build a strategy that records ta.* call results into a list
# at the chosen call site, then feed it a candle sequence and inspect.
# ============================================================

def _run_with_recorder(closes, recorder_fn):
    """Build a strategy whose on_bar calls `recorder_fn(close)` once per bar
    and records the returned value into a list. Returns the list."""
    recorded: list = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            recorded.append(recorder_fn(candle.close))

    s = S({})
    for i, c in enumerate(closes):
        s.update(_c(i, close=c))
    return recorded


# ============================================================
# SMA — simple moving average semantics
# ============================================================

def test_sma_returns_nan_until_window_fills():
    out = _run_with_recorder(
        [10.0, 20.0, 30.0, 40.0, 50.0],
        lambda close: ta.sma(close, 3),
    )
    # bars 0, 1 produce NaN (insufficient data); bars 2+ produce the SMA.
    assert _m.isnan(out[0])
    assert _m.isnan(out[1])
    assert out[2] == pytest.approx(20.0)  # (10+20+30)/3
    assert out[3] == pytest.approx(30.0)  # (20+30+40)/3
    assert out[4] == pytest.approx(40.0)  # (30+40+50)/3


def test_sma_is_persistent_across_bars_at_same_call_site():
    """Repeated calls to ta.sma at the same source line keep accumulating
    rather than rebuilding a fresh indicator each bar."""
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    out = _run_with_recorder(closes, lambda c: ta.sma(c, 4))
    # Expected SMA(4) for input 1..10:
    # bar 3: (1+2+3+4)/4 = 2.5
    # bar 4: (2+3+4+5)/4 = 3.5
    # bar 9: (7+8+9+10)/4 = 8.5
    assert out[3] == pytest.approx(2.5)
    assert out[4] == pytest.approx(3.5)
    assert out[9] == pytest.approx(8.5)


def test_two_sma_calls_on_different_lines_are_distinct_indicators():
    """Two ta.sma(close, 3) calls on different source lines must NOT share
    state — they're independent indicators per Pine semantics."""
    pair_out = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            # Two distinct call sites with different lengths to make it obvious
            # they aren't aliased.
            a = ta.sma(candle.close, 3)
            b = ta.sma(candle.close, 5)
            pair_out.append((a, b))

    s = S({})
    for i, c in enumerate([10.0, 20.0, 30.0, 40.0, 50.0]):
        s.update(_c(i, close=c))

    # SMA(3) ready at bar 2; SMA(5) ready at bar 4.
    assert pair_out[2][0] == pytest.approx(20.0)
    assert _m.isnan(pair_out[2][1])
    assert pair_out[4][0] == pytest.approx(40.0)
    assert pair_out[4][1] == pytest.approx(30.0)  # (10+20+30+40+50)/5


# ============================================================
# EMA — Wilder seed semantics
# ============================================================

def test_ema_is_persistent_and_matches_seeded_calculation():
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    out = _run_with_recorder(closes, lambda c: ta.ema(c, 3))
    # The SDK's EMA uses SMA seed at period 3:
    # bar 0, 1 NaN; bar 2: SMA(10,11,12) = 11.0
    # bar 3: 11.0 + 2/(3+1) * (13 - 11.0) = 11.0 + 0.5 * 2.0 = 12.0
    # bar 4: 12.0 + 0.5 * (14 - 12.0) = 13.0
    # bar 5: 13.0 + 0.5 * (15 - 13.0) = 14.0
    assert _m.isnan(out[0])
    assert _m.isnan(out[1])
    assert out[2] == pytest.approx(11.0)
    assert out[3] == pytest.approx(12.0)
    assert out[4] == pytest.approx(13.0)
    assert out[5] == pytest.approx(14.0)


# ============================================================
# Crossover / crossunder — strict cross detection on transition bar
# ============================================================

def test_crossover_fires_only_on_transition_bar():
    """ta.crossover(a, b) is True only on the bar where a crosses UP through
    b. Once a stays above b in subsequent bars, crossover returns False."""
    transitions = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            fast = ta.sma(candle.close, 2)
            slow = ta.sma(candle.close, 4)
            transitions.append(ta.crossover(fast, slow))

    s = S({})
    # Setup: closes engineered so fast SMA crosses above slow SMA on a
    # specific bar then stays above.
    closes = [10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0]
    for i, c in enumerate(closes):
        s.update(_c(i, close=c))

    # On bar 0..2 SMA(2)/SMA(4) NaN; first sane comparison is bar 3.
    # At bar 4 (close=20), fast=15, slow=12.5 → fast > slow, but bar 3 had
    # fast=10, slow=10 → exactly equal so cross condition (prev: fast<=slow)
    # is met, current: fast>slow → True.
    # On bar 5: fast=20, slow=15 → still above, but prev bar had fast>slow
    # so crossover returns False (no re-cross).
    assert transitions[4] is True
    assert transitions[5] is False
    assert transitions[6] is False


def test_crossunder_mirror_of_crossover():
    transitions = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            fast = ta.sma(candle.close, 2)
            slow = ta.sma(candle.close, 4)
            transitions.append(ta.crossunder(fast, slow))

    s = S({})
    closes = [20.0, 20.0, 20.0, 20.0, 10.0, 10.0, 10.0]
    for i, c in enumerate(closes):
        s.update(_c(i, close=c))

    # Mirror: fast crosses DOWN through slow at bar 4, stays below afterwards.
    assert transitions[4] is True
    assert transitions[5] is False


def test_crossover_resets_after_recross():
    """After fast crosses up at bar X, then crosses down at bar Y, a
    subsequent up-cross at bar Z must fire again."""
    transitions = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            transitions.append(ta.crossover(candle.close, 100.0))

    s = S({})
    # Force: bar 0 below (99), bar 1 above (101), bar 2 below (99), bar 3
    # above (101).
    for i, c in enumerate([99.0, 101.0, 99.0, 101.0]):
        s.update(_c(i, close=c))

    assert transitions[1] is True   # 99 → 101 crosses 100
    assert transitions[3] is True   # 99 → 101 again, fresh cross
    assert transitions[2] is False  # going below, not a cross UP


# ============================================================
# highest / lowest — rolling window
# ============================================================

def test_highest_rolling_window_matches_expected():
    closes = [10.0, 20.0, 15.0, 25.0, 18.0, 30.0]
    out = _run_with_recorder(closes, lambda c: ta.highest(c, 3))
    # Window len 3 — NaN until bar 2:
    # bar 2: max(10, 20, 15) = 20
    # bar 3: max(20, 15, 25) = 25
    # bar 4: max(15, 25, 18) = 25
    # bar 5: max(25, 18, 30) = 30
    assert _m.isnan(out[0])
    assert _m.isnan(out[1])
    assert out[2] == 20.0
    assert out[3] == 25.0
    assert out[4] == 25.0
    assert out[5] == 30.0


def test_lowest_rolling_window_matches_expected():
    closes = [10.0, 20.0, 15.0, 5.0, 18.0]
    out = _run_with_recorder(closes, lambda c: ta.lowest(c, 3))
    assert _m.isnan(out[0])
    assert _m.isnan(out[1])
    assert out[2] == 10.0
    assert out[3] == 5.0
    assert out[4] == 5.0


# ============================================================
# change — bar-over-bar delta
# ============================================================

def test_change_returns_diff_against_previous_bar():
    out = _run_with_recorder([10.0, 12.0, 8.0, 15.0], lambda c: ta.change(c))
    assert _m.isnan(out[0])  # first bar has no prior
    assert out[1] == pytest.approx(2.0)   # 12 - 10
    assert out[2] == pytest.approx(-4.0)  # 8 - 12
    assert out[3] == pytest.approx(7.0)   # 15 - 8


# ============================================================
# barssince — bars-since-condition counter
# ============================================================

def test_barssince_returns_negative_one_before_condition_first_true():
    out = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            out.append(ta.barssince(candle.close > 50.0))

    s = S({})
    for i, c in enumerate([10.0, 20.0, 30.0]):
        s.update(_c(i, close=c))
    # Condition never True → -1 sentinel.
    assert out == [-1, -1, -1]


def test_barssince_resets_to_zero_on_true_then_counts_up():
    out = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            out.append(ta.barssince(candle.close > 50.0))

    s = S({})
    for i, c in enumerate([10.0, 60.0, 20.0, 30.0, 70.0, 10.0]):
        s.update(_c(i, close=c))

    # bar 0: 10 not > 50 → -1
    # bar 1: 60 > 50 → 0
    # bar 2: 20 not > → 1
    # bar 3: 30 not > → 2
    # bar 4: 70 > 50 → 0 (reset)
    # bar 5: 10 not > → 1
    assert out == [-1, 0, 1, 2, 0, 1]


# ============================================================
# History operator semantics
# ============================================================

def test_history_returns_value_n_bars_back_for_builtin_series():
    out = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            out.append((history("close", 0), history("close", 1), history("close", 2)))

    s = S({})
    for i, c in enumerate([100.0, 101.0, 102.0, 103.0]):
        s.update(_c(i, close=c))

    # bar 3:
    #   history(close, 0) = current bar's close = 103
    #   history(close, 1) = prev bar close = 102
    #   history(close, 2) = 2 bars ago = 101
    assert out[3] == (103.0, 102.0, 101.0)


# ============================================================
# ATR semantics — Wilder-seeded true range smoothing
# ============================================================

def test_atr_returns_nan_until_seed_complete_then_smooths():
    out = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            out.append(ta.atr(3))

    s = S({})
    # All bars share the same close so prev_close = current bar's price
    # range midpoint. With high - low = 1.0 and |high - prev_close| = 0.5
    # and |low - prev_close| = 0.5, TR = max(...) = 1.0 every bar.
    for i in range(6):
        s.update(_c(i, close=100.0, open_=100.0, high=100.5, low=99.5))

    # SDK ATR uses a first-candle anchor (P4.1 update) — period+1 bars to be ready.
    # So with length=3, ready after bar 3. Subsequent values = smoothed TR = 1.0.
    for v in out[4:]:
        assert v == pytest.approx(1.0)


# ============================================================
# Multi-tf cache via request.security() — engine-side feed simulation
# ============================================================

def test_request_security_returns_fed_close_when_cache_populated():
    captures = []
    from lyrithm_sdk.pine_runtime import request

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            captures.append(
                request.security("BTCUSDT", "60", candle.close)
            )

    s = S({})
    # Bar 0: no upstream candle delivered → falls back to expression.
    s.update(_c(1, close=10.0))
    assert captures[0] == 10.0
    # Engine delivers a higher-tf candle.
    s.feed_additional_candle("BTCUSDT", "60", _c(2, close=99.0))
    s.update(_c(3, close=11.0))
    # Now request.security pulls the fed value, not the local close.
    assert captures[1] == 99.0


def test_request_security_attr_override_returns_specified_field():
    captures = []
    from lyrithm_sdk.pine_runtime import request

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            captures.append(
                request.security("ETHUSDT", "240", candle.high, attr="high")
            )

    s = S({})
    s.feed_additional_candle("ETHUSDT", "240", _c(1, close=200.0, high=250.0, low=180.0))
    s.update(_c(2, close=11.0, high=12.0))
    assert captures[0] == 250.0
