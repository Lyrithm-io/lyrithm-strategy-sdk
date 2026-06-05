# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""P4.2 — smoke tests for the 3 new bundled example strategies
(rsi-mean-reversion, donchian-breakout, macd-divergence)."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

from lyrithm_sdk import Candle
from lyrithm_sdk.manifest import load_manifest
from lyrithm_sdk.testing import BacktestRunner

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _load_example(name: str):
    path = EXAMPLES / name / "strategy.py"
    spec = importlib.util.spec_from_file_location(
        f"_p42_{name.replace('-', '_')}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sine_candles(n: int, period: float = 12.0, amp: float = 10.0):
    """Up/down sine wave so trend-following + mean-reversion strategies
    both fire entry signals during a single run."""
    out = []
    for i in range(n):
        base = 100.0 + amp * math.sin(i / period)
        out.append(
            Candle(
                timestamp=i * 60_000,
                open=base,
                high=base + 0.5,
                low=base - 0.5,
                close=base + 0.2 * math.cos(i / 4.0),
                volume=1000.0,
            )
        )
    return out


def _breakout_candles(n: int):
    """Step-up, step-down series so Donchian + MACD divergence print fresh
    highs/lows the rules can fire on."""
    out = []
    base = 100.0
    for i in range(n):
        if i < n // 3:
            base = 100.0
        elif i < 2 * n // 3:
            base = 100.0 + (i - n // 3) * 0.6  # uptrend leg
        else:
            base = 100.0 + (n // 3) * 0.6 - (i - 2 * n // 3) * 0.6  # downtrend leg
        out.append(
            Candle(
                timestamp=i * 60_000,
                open=base,
                high=base + 0.6,
                low=base - 0.6,
                close=base,
                volume=1000.0,
            )
        )
    return out


# ============================================================
# RSI Mean Reversion
# ============================================================


def test_rsi_mean_reversion_runs_end_to_end():
    mod = _load_example("rsi-mean-reversion")
    strategy = mod.create_strategy({"rsi_period": 4, "atr_period": 4})
    report = BacktestRunner(strategy).run(_sine_candles(300))
    assert report.candles_processed == 300
    # On an oscillating sine wave with a tight RSI period, cross-back
    # signals must fire at least once.
    assert len(report.signals) > 0


def test_rsi_mean_reversion_resets_cleanly():
    mod = _load_example("rsi-mean-reversion")
    strategy = mod.create_strategy({})
    BacktestRunner(strategy).run(_sine_candles(120))
    assert strategy.is_ready()
    strategy.reset()
    assert not strategy.is_ready()


def test_rsi_mean_reversion_manifest_loads():
    m = load_manifest(EXAMPLES / "rsi-mean-reversion" / "lyrithm.yaml")
    assert m.name == "rsi-mean-reversion"
    assert m.language == "python"
    assert m.default_config["rsi_period"] == 14
    assert m.default_config["oversold_threshold"] == 30.0


def test_rsi_mean_reversion_warmup_blocks_signals_under_min_bars():
    """A buyer who restarts the engine mid-bar must not see a signal on
    the very first tick after boot — the 4-bar floor is the safety net."""
    mod = _load_example("rsi-mean-reversion")
    strategy = mod.create_strategy({"rsi_period": 2, "atr_period": 2})
    # Manually feed 3 candles — under the min warmup floor.
    for i in range(3):
        strategy.update(Candle(i, 100, 101, 99, 100, 1000))
    assert not strategy.is_ready()
    assert strategy.check_long_entry() == 0
    assert strategy.check_short_entry() == 0


# ============================================================
# Donchian Breakout
# ============================================================


def test_donchian_breakout_runs_end_to_end():
    mod = _load_example("donchian-breakout")
    strategy = mod.create_strategy({"channel_period": 5, "atr_period": 5})
    report = BacktestRunner(strategy).run(_breakout_candles(150))
    assert report.candles_processed == 150
    # The step-up / step-down legs must trigger Donchian breakouts.
    assert len(report.signals) > 0


def test_donchian_breakout_manifest_loads():
    m = load_manifest(EXAMPLES / "donchian-breakout" / "lyrithm.yaml")
    assert m.name == "donchian-breakout"
    assert m.default_config["channel_period"] == 20


def test_donchian_breakout_clamps_channel_period_to_minimum():
    mod = _load_example("donchian-breakout")
    # channel_period=1 would degenerate to "close > last bar high" which
    # fires on every bar. Constructor clamps to 2.
    strategy = mod.create_strategy({"channel_period": 1})
    assert strategy.channel_period == 2


def test_donchian_breakout_resets_cleanly():
    mod = _load_example("donchian-breakout")
    strategy = mod.create_strategy({"channel_period": 5})
    BacktestRunner(strategy).run(_breakout_candles(120))
    assert strategy.is_ready()
    strategy.reset()
    assert not strategy.is_ready()


# ============================================================
# MACD Divergence
# ============================================================


def test_macd_divergence_runs_end_to_end():
    mod = _load_example("macd-divergence")
    strategy = mod.create_strategy({
        "macd_fast": 4,
        "macd_slow": 8,
        "macd_signal": 3,
        "divergence_lookback": 5,
        "atr_period": 5,
    })
    report = BacktestRunner(strategy).run(_sine_candles(200))
    assert report.candles_processed == 200


def test_macd_divergence_rejects_invalid_fast_vs_slow():
    mod = _load_example("macd-divergence")
    with pytest.raises(ValueError):
        mod.create_strategy({"macd_fast": 26, "macd_slow": 12})


def test_macd_divergence_manifest_loads():
    m = load_manifest(EXAMPLES / "macd-divergence" / "lyrithm.yaml")
    assert m.name == "macd-divergence"
    assert m.default_config["macd_fast"] == 12
    assert m.default_config["macd_slow"] == 26


def test_macd_divergence_clamps_lookback_to_minimum():
    mod = _load_example("macd-divergence")
    # Lookback=2 would make the "any prior" check degenerate; clamp to 4.
    strategy = mod.create_strategy({"divergence_lookback": 2})
    assert strategy.divergence_lookback == 4


def test_macd_divergence_resets_cleanly():
    mod = _load_example("macd-divergence")
    strategy = mod.create_strategy({})
    BacktestRunner(strategy).run(_sine_candles(120))
    strategy.reset()
    assert not strategy.is_ready()
    # Internal histogram buffer must be empty after reset so the next
    # session doesn't see stale divergence carryover.
    assert len(strategy._closes) == 0
    assert len(strategy._histograms) == 0


# ============================================================
# All-3 config schema check
# ============================================================


@pytest.mark.parametrize(
    "name", ["rsi-mean-reversion", "donchian-breakout", "macd-divergence"]
)
def test_config_schema_json_is_well_formed(name):
    import json
    schema_path = EXAMPLES / name / "config_schema.json"
    assert schema_path.is_file(), f"missing config_schema.json for {name}"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "title" in schema and "groups" in schema
    for group in schema["groups"]:
        assert "name" in group and "fields" in group
        for field_name, field_def in group["fields"].items():
            assert "type" in field_def
            assert "default" in field_def
            assert "label" in field_def
