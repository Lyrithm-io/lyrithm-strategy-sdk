# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""End-to-end smoke test of the BacktestRunner using the bundled ema-cross example."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from lyrithm_sdk import Candle
from lyrithm_sdk.testing import BacktestRunner

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _load_example(name: str):
    path = EXAMPLES / name / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_example_{name.replace('-', '_')}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_candles(n: int = 200):
    """Sine-wave-ish series with up/down legs so EMA-cross fires both sides."""
    import math
    out = []
    for i in range(n):
        base = 100 + 10 * math.sin(i / 12.0)
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


def test_ema_cross_runs_and_emits_signals():
    mod = _load_example("ema-cross")
    strategy = mod.create_strategy({"ema_fast": 5, "ema_slow": 20})
    report = BacktestRunner(strategy).run(_synthetic_candles(300))
    assert report.candles_processed == 300
    # A sine wave with these EMAs must produce at least one signal
    assert len(report.signals) > 0


def test_ema_cross_state_resets_cleanly():
    mod = _load_example("ema-cross")
    strategy = mod.create_strategy({"ema_fast": 5, "ema_slow": 20})
    BacktestRunner(strategy).run(_synthetic_candles(100))
    assert strategy.is_ready()
    strategy.reset()
    assert not strategy.is_ready()
