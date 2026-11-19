# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Pine plot() and color.* — values a chart draws, kept per bar and never
part of the signal state."""
from __future__ import annotations

import pytest

from lyrithm_sdk import Candle
from lyrithm_sdk.pine_runtime import MAX_PLOTS, PineStrategy, color, plot, strategy, ta


def _candle(t: int, c: float) -> Candle:
    return Candle(timestamp=t, open=c, high=c, low=c, close=c, volume=1.0)


class _Plotter(PineStrategy):
    """Plots a fast SMA, an untitled close, and a third line only on even bars."""

    def on_bar(self, candle, *, close, open, high, low, volume, time, bar_index):
        fast = ta.sma(close, 2)
        plot(fast, "SMA 2", color=color.blue)
        plot(close)
        if bar_index % 2 == 0:
            plot(close * 2, title="Double", color=color.new(color.red, 50))


def test_each_plot_reports_this_bars_value_in_first_plotted_order():
    s = _Plotter({})
    s.update(_candle(1, 10.0))
    s.update(_candle(2, 20.0))

    assert s.get_plots() == [
        {"name": "SMA 2", "value": 15.0, "color": "#2196F3"},
        {"name": "Plot", "value": 20.0, "color": None},
        {"name": "Double", "value": None, "color": None},
    ]


def test_a_plot_not_reached_this_bar_is_a_gap_and_comes_back():
    s = _Plotter({})
    values = []
    for i, c in enumerate([10.0, 20.0, 30.0]):
        s.update(_candle(i, c))
        values.append(s.get_plots()[2]["value"])
    assert values == [20.0, None, 60.0]


def test_na_and_non_numbers_plot_as_gaps():
    class _Na(PineStrategy):
        def on_bar(self, candle, *, close, open, high, low, volume, time, bar_index):
            plot(float("nan"), "nan")
            plot(None, "none")
            plot(True, "bool")
            plot(float("inf"), "inf")

    s = _Na({})
    s.update(_candle(1, 1.0))
    assert [p["value"] for p in s.get_plots()] == [None, None, None, None]


def test_untitled_and_repeated_titles_get_distinct_names():
    class _Same(PineStrategy):
        def on_bar(self, candle, *, close, open, high, low, volume, time, bar_index):
            plot(close)
            plot(close)
            plot(close, "x")
            plot(close, "x")

    s = _Same({})
    s.update(_candle(1, 1.0))
    assert [p["name"] for p in s.get_plots()] == ["Plot", "Plot 2", "x", "x 2"]


def test_one_call_site_in_a_loop_is_one_plot():
    class _Loop(PineStrategy):
        def on_bar(self, candle, *, close, open, high, low, volume, time, bar_index):
            for i in range(3):
                plot(close + i, f"p{i}")

    s = _Loop({})
    s.update(_candle(1, 1.0))
    assert s.get_plots() == [{"name": "p0", "value": 3.0, "color": None}]


def test_plots_beyond_the_cap_are_ignored():
    # Generated code has one line per plot() call; build such a body.
    lines = "\n".join(f"    plot(close + {i}, 'p{i}')" for i in range(MAX_PLOTS + 4))
    namespace = {"plot": plot}
    exec(f"def body(close):\n{lines}\n", namespace)

    class _Many(PineStrategy):
        def on_bar(self, candle, *, close, open, high, low, volume, time, bar_index):
            namespace["body"](close)

    s = _Many({})
    s.update(_candle(1, 1.0))
    plots = s.get_plots()
    assert len(plots) == MAX_PLOTS
    assert plots[-1]["name"] == f"p{MAX_PLOTS - 1}"


def test_plotting_does_not_change_the_signals():
    class _Trader(PineStrategy):
        def __init__(self, config, with_plot):
            super().__init__(config)
            self.with_plot = with_plot

        def on_bar(self, candle, *, close, open, high, low, volume, time, bar_index):
            if self.with_plot:
                plot(close, "close")
            if bar_index == 1:
                strategy.entry("L", strategy.long)

    a, b = _Trader({}, True), _Trader({}, False)
    for i in range(3):
        a.update(_candle(i, 100.0 + i))
        b.update(_candle(i, 100.0 + i))
        assert a.check_long_entry() == b.check_long_entry()
    assert b.get_plots() == []


def test_reset_forgets_the_plots():
    s = _Plotter({})
    s.update(_candle(1, 10.0))
    s.reset()
    assert s.get_plots() == []


def test_plot_outside_on_bar_raises():
    with pytest.raises(RuntimeError):
        plot(1.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (color.new(color.red, 0), "#FF5252"),
        (color.new(color.red, 100), "#FF525200"),
        (color.new("#00897B", 50), "#00897B80"),
        (color.rgb(255, 128, 0), "#FF8000"),
        (color.rgb(300, -5, 0, 20), "#FF0000CC"),
        (color.new("not-a-colour", 50), "not-a-colour"),
    ],
)
def test_colors_are_hex(value, expected):
    assert value == expected
