# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
from __future__ import annotations

from lyrithm_sdk import Candle, Signal, SignalSide, TradeResult


def test_candle_bullish_bearish():
    c = Candle(timestamp=0, open=100, high=105, low=99, close=104, volume=1.0)
    assert c.is_bullish() and not c.is_bearish()
    c2 = Candle(timestamp=0, open=100, high=101, low=95, close=96, volume=1.0)
    assert c2.is_bearish() and not c2.is_bullish()


def test_candle_typical_price():
    c = Candle(timestamp=0, open=100, high=110, low=90, close=100, volume=1.0)
    assert c.typical_price == 100.0


def test_signal_defaults():
    s = Signal(side=SignalSide.LONG)
    assert s.rule_id == 1
    assert s.risk_multiplier == 1.0
    assert s.metadata == {}


def test_trade_result_fields():
    t = TradeResult(side=SignalSide.SHORT, entry_price=100, exit_price=98, pnl=2.0, won=True)
    assert t.side == SignalSide.SHORT
    assert t.won is True
    assert t.pnl == 2.0
