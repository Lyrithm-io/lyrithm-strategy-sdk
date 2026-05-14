# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""
Strategy contract — mirrors `com.lyrithm.strategy.api.Strategy` (Java) so the
same conceptual strategy exists in every supported language.

A strategy module exposed to the loader must either:
  1. expose a callable `create_strategy(config: Mapping[str, Any]) -> Strategy`, or
  2. declare exactly one top-level subclass of `Strategy` with a single
     positional `config` (dict) or no-arg constructor.

The loader prefers (1) when present.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from .models import Candle, TradeResult


class Strategy(ABC):
    """Base class for all Lyrithm strategies."""

    # ---- Lifecycle ----
    @abstractmethod
    def update(self, candle: Candle) -> None:
        """Feed one closed candle into the strategy's indicators and state."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Returns True when enough candles have been seen to produce signals."""

    @abstractmethod
    def reset(self) -> None:
        """Reset all internal state to a fresh post-construction state."""

    # ---- Entry signals (return 0 = no signal; >0 = rule id that fired) ----
    @abstractmethod
    def check_long_entry(self) -> int: ...

    @abstractmethod
    def check_short_entry(self) -> int: ...

    # ---- Risk levels ----
    @abstractmethod
    def calculate_long_stop_loss(self) -> float: ...

    @abstractmethod
    def calculate_short_stop_loss(self) -> float: ...

    @abstractmethod
    def get_dynamic_reward_ratio(self) -> float: ...

    @abstractmethod
    def get_dynamic_leverage(self) -> int: ...

    def get_dynamic_risk_multiplier(self) -> float:
        """Override to return > 1.0 for high-conviction signals (e.g. boost zones).
        The platform PositionManager multiplies sizer output by this value."""
        return 1.0

    # ---- Diagnostics ----
    def get_adx(self) -> float:
        return 0.0

    def get_market_regime(self) -> str:
        return "N/A"

    # ---- Optional event hooks (default no-op) ----
    def on_trade_close(self, result: TradeResult) -> None:
        """Called after each closed trade. Override to maintain stateful sizing
        (e.g. anti-martingale streak counters)."""
        return None

    def on_destroy(self) -> None:
        """Called once before instance teardown. Override to release resources."""
        return None

    # ---- State persistence ----
    def export_state(self) -> Mapping[str, Any]:
        """Serialize internal state to a JSON-safe dict (for hot-reload, crash
        recovery). Default: stateless (empty dict)."""
        return {}

    def import_state(self, state: Mapping[str, Any]) -> None:
        """Inverse of export_state. Default: no-op."""
        return None
