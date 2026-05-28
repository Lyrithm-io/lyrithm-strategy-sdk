# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Sanity checks on bundled indicators. Numeric parity vs Java is asserted in
vegas-core's golden tests; here we just guard the public contract."""
from __future__ import annotations

import pytest

from lyrithm_sdk import Candle
from lyrithm_sdk.indicators import ADX, ATR, EMA, SMA, MarketRegime, Regime


def _candle(t: int, o: float, h: float, l: float, c: float, v: float = 1000.0) -> Candle:
    return Candle(timestamp=t, open=o, high=h, low=l, close=c, volume=v)


def test_ema_not_ready_until_period_seeded():
    ema = EMA(5)
    for i, price in enumerate([10.0, 11.0, 12.0, 13.0]):
        ema.update(price)
        assert not ema.is_ready(), f"should not be ready after {i + 1} updates"
    ema.update(14.0)
    assert ema.is_ready()
    assert ema.get_value() == pytest.approx(12.0)


def test_ema_recursive_after_seed():
    ema = EMA(3)
    for p in [1.0, 2.0, 3.0]:
        ema.update(p)
    assert ema.is_ready()
    seed = ema.get_value()
    ema.update(4.0)
    multiplier = 2.0 / (3 + 1)
    assert ema.get_value() == pytest.approx(seed + (4.0 - seed) * multiplier)


def test_ema_export_import_state_roundtrip():
    a = EMA(4)
    for p in [10, 12, 11, 13, 14, 15]:
        a.update(p)
    b = EMA(4)
    b.import_state(a.export_state())
    assert b.get_value() == a.get_value()
    assert b.is_ready() == a.is_ready()


def test_ema_invalid_period():
    with pytest.raises(ValueError):
        EMA(0)


# ============================================================
# SMA — added in S4 alongside the sma-crossover example
# ============================================================


def test_sma_not_ready_until_window_filled():
    sma = SMA(4)
    for p in [10.0, 11.0, 12.0]:
        sma.update(p)
        assert not sma.is_ready()
    sma.update(13.0)
    assert sma.is_ready()
    assert sma.get_value() == pytest.approx(11.5)


def test_sma_window_evicts_oldest_after_full():
    sma = SMA(3)
    for p in [10.0, 20.0, 30.0]:
        sma.update(p)
    assert sma.get_value() == pytest.approx(20.0)
    sma.update(60.0)   # evicts 10, window = [20, 30, 60]
    assert sma.get_value() == pytest.approx((20 + 30 + 60) / 3.0)


def test_sma_reset_clears_state():
    sma = SMA(2)
    sma.update(5.0)
    sma.update(7.0)
    assert sma.is_ready()
    sma.reset()
    assert not sma.is_ready()
    assert sma.get_value() == 0.0


def test_sma_export_import_state_roundtrip():
    a = SMA(4)
    for p in [10.0, 12.0, 11.0, 13.0, 14.0, 15.0]:
        a.update(p)
    b = SMA(4)
    b.import_state(a.export_state())
    assert b.is_ready()
    assert b.get_value() == pytest.approx(a.get_value())
    # Subsequent update on b advances independently
    b.update(20.0)
    assert b.get_value() != a.get_value()


def test_sma_invalid_period():
    with pytest.raises(ValueError):
        SMA(0)
    with pytest.raises(ValueError):
        SMA(-3)


def test_adx_warms_up_then_produces_positive_value():
    adx = ADX(14)
    base = 100.0
    for i in range(60):
        # Construct a clear uptrend so ADX rises
        price = base + i * 0.5
        adx.update(_candle(i, price, price + 0.6, price - 0.2, price + 0.4))
    assert adx.is_ready()
    assert adx.get_value() > 0


def test_atr_seeds_after_period():
    atr = ATR(5)
    for i in range(4):
        atr.update(_candle(i, 100, 102, 99, 101))
    assert not atr.is_ready()
    atr.update(_candle(4, 100, 102, 99, 101))
    assert atr.is_ready()
    assert atr.get_value() > 0


def test_market_regime_classifies_strong_trend_when_adx_high():
    regime = MarketRegime(strong_trend_threshold=40, moderate_trend_threshold=25)
    for i in range(30):
        regime.update(_candle(i, 100, 101, 99, 100), adx_value=0.0)
    assert regime.is_ready()
    regime.update(_candle(30, 100, 101, 99, 100), adx_value=55.0)
    assert regime.get_current_regime() == Regime.STRONG_TREND


def test_market_regime_classifies_moderate_trend():
    regime = MarketRegime(strong_trend_threshold=40, moderate_trend_threshold=25)
    for i in range(30):
        regime.update(_candle(i, 100, 101, 99, 100), adx_value=0.0)
    regime.update(_candle(30, 100, 101, 99, 100), adx_value=30.0)
    assert regime.get_current_regime() == Regime.MODERATE_TREND
