# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""P5.1e tests — pine_runtime adapter MVP. Validates that emitted code can
be subclassed + run via the polled Strategy API. Indicator numerical
parity, request.security multi-tf delivery, and varip tick semantics are
follow-up sprints."""
from __future__ import annotations

import math as _m

import pytest

from lyrithm_sdk import Candle
from lyrithm_sdk.pine_runtime import (
    PineStrategy,
    history,
    na,
    nz,
    strategy,
    ta,
    request,
)


def _candle(t: int, c: float, o: float = None, h: float = None,
            l: float = None, v: float = 1000.0) -> Candle:
    if o is None:
        o = c
    if h is None:
        h = max(o, c)
    if l is None:
        l = min(o, c)
    return Candle(timestamp=t, open=o, high=h, low=l, close=c, volume=v)


# ============================================================
# Minimal generated-code mock that exercises the adapter surface.
# ============================================================

class _MockGenerated(PineStrategy):
    PINE_VERSION = 5
    STRATEGY_ARGS = {"title": "Mock", "overlay": True}

    def __init__(self, config=None):
        super().__init__(config or {})
        self.var_x = 0
        self.observed_kwargs = None

    def on_bar(self, candle, *, close, open, high, low, volume, time, bar_index):
        # Capture so the test can inspect what the runtime injected.
        self.observed_kwargs = dict(
            close=close, open=open, high=high, low=low,
            volume=volume, time=time, bar_index=bar_index,
        )


def test_subclass_instantiates_and_on_bar_receives_pine_kwargs():
    s = _MockGenerated({})
    s.update(_candle(1, c=100.0, o=99.0, h=101.0, l=98.0))
    assert s.observed_kwargs["close"] == 100.0
    assert s.observed_kwargs["open"] == 99.0
    assert s.observed_kwargs["high"] == 101.0
    assert s.observed_kwargs["low"] == 98.0
    assert s.observed_kwargs["bar_index"] == 0


def test_bar_index_increments_per_update():
    s = _MockGenerated({})
    for i in range(3):
        s.update(_candle(i, c=100.0 + i))
    assert s.observed_kwargs["bar_index"] == 2


def test_strategy_entry_sets_pending_long_signal():
    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            strategy.entry("L", strategy.long)

    s = S({})
    s.update(_candle(1, c=100.0))
    assert s.check_long_entry() == 1
    assert s.check_short_entry() == 0


def test_strategy_entry_short_direction_routes_to_short_signal():
    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            strategy.entry("S", strategy.short)

    s = S({})
    s.update(_candle(1, c=100.0))
    assert s.check_long_entry() == 0
    assert s.check_short_entry() == 1


def test_pending_signals_clear_at_start_of_next_bar():
    class S(PineStrategy):
        def __init__(self, config=None):
            super().__init__(config or {})
            self.fire = True

        def on_bar(self, candle, **kw):
            if self.fire:
                strategy.entry("L", strategy.long)
                self.fire = False

    s = S({})
    s.update(_candle(1, c=100.0))
    assert s.check_long_entry() == 1
    s.update(_candle(2, c=101.0))
    assert s.check_long_entry() == 0


def test_history_returns_none_until_buffer_fills():
    captures = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            captures.append(history("close", 1))

    s = S({})
    s.update(_candle(1, c=100.0))  # first bar: no prior
    s.update(_candle(2, c=101.0))  # second bar: prior close = 100.0
    s.update(_candle(3, c=102.0))  # third bar: prior close = 101.0
    assert captures[0] is None
    assert captures[1] == 100.0
    assert captures[2] == 101.0


def test_history_past_buffer_depth_returns_none():
    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            self.captured = history("close", 999)

    s = S({})
    s.update(_candle(1, c=100.0))
    assert s.captured is None


def test_nz_replaces_nan_and_none_with_default():
    assert nz(None) == 0.0
    assert nz(None, 42.0) == 42.0
    assert nz(float("nan"), 7.0) == 7.0
    assert nz(123.4) == 123.4
    assert nz(0.0) == 0.0


def test_na_detects_nan_and_none():
    assert na(None) is True
    assert na(float("nan")) is True
    assert na(0.0) is False
    assert na(1.0) is False


def test_strategy_entry_with_unknown_direction_raises():
    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            strategy.entry("bad", "diagonal")

    s = S({})
    with pytest.raises(ValueError, match="unknown direction"):
        s.update(_candle(1, c=100.0))


def test_strategy_close_appends_to_pending_close_ids():
    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            strategy.close("L")
            strategy.close("S")

    s = S({})
    s.update(_candle(1, c=100.0))
    assert s._state.pending_close_ids == ["L", "S"]


def test_request_security_echoes_expression_in_mvp():
    # P5.1e MVP: request.security() just returns the passed-in expression
    # unchanged. Real multi-tf delivery lands in a P5.1e follow-up sprint.
    assert request.security("BTCUSDT", "60", 42.0) == 42.0


def test_ta_sma_proxies_to_indicator_value():
    # Returns NaN until indicator warms up.
    v1 = ta.sma(100.0, 3)
    assert _m.isnan(v1)
    # Single-call surface — real backtesting needs persistent indicators
    # across bars. MVP exercise only.


def test_calculate_stop_loss_falls_back_to_one_percent_on_no_explicit_stop():
    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            strategy.entry("L", strategy.long)

    s = S({})
    s.update(_candle(1, c=100.0))
    assert s.calculate_long_stop_loss() == pytest.approx(99.0)
    assert s.calculate_short_stop_loss() == pytest.approx(101.0)


def test_is_ready_flips_after_first_bar():
    s = _MockGenerated({})
    assert not s.is_ready()
    s.update(_candle(1, c=100.0))
    assert s.is_ready()


def test_reset_clears_state_and_bar_index():
    s = _MockGenerated({})
    s.update(_candle(1, c=100.0))
    s.update(_candle(2, c=101.0))
    s.reset()
    assert s._bar_index == 0
    assert not s.is_ready()


def test_reset_clears_history_buffer():
    captures = []

    class S(PineStrategy):
        def on_bar(self, candle, **kw):
            captures.append(history("close", 1))

    s = S({})
    s.update(_candle(1, c=100.0))  # captures None (no prior)
    s.update(_candle(2, c=101.0))  # captures 100.0
    assert captures == [None, 100.0]
    s.reset()
    captures.clear()
    s.update(_candle(3, c=200.0))  # post-reset: no prior → None
    s.update(_candle(4, c=201.0))  # captures 200.0
    assert captures == [None, 200.0]
