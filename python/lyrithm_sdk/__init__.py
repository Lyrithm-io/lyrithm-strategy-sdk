# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""
Lyrithm Strategy SDK — Python.

Public surface (kept intentionally small for forward compatibility):

    from lyrithm_sdk import Strategy, Candle, Signal, TradeResult
    from lyrithm_sdk.indicators import EMA, ADX, ATR, MarketRegime, Regime

The same `.py` strategy file runs unchanged in:
  * the SDK's local BacktestRunner (offline development),
  * lyrithm-sandbox (paper-trade / backtest service),
  * vegas-core (Lyrithm live trading platform).
"""
from __future__ import annotations

from .models import Candle, Signal, SignalSide, TradeResult
from .strategy import Strategy

__all__ = [
    "Strategy",
    "Candle",
    "Signal",
    "SignalSide",
    "TradeResult",
]

__version__ = "0.1.0"
