# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""
Pine v5 runtime adapter — lights up Python source emitted by the
lyrithm-engine PineToPythonCodegen (P5.1b) by providing the namespaces and
helpers the generated code references.

Generated code looks roughly like::

    from lyrithm_sdk.pine_runtime import (
        PineStrategy, ta, math, strategy, request, input,
        history, nz, na, persistent,
    )

    class GeneratedStrategy(PineStrategy):
        PINE_VERSION = 5
        STRATEGY_ARGS = {"title": "EMA Cross", "overlay": True}

        def __init__(self, config):
            super().__init__(config or {})
            self.var_bars_held = 0

        def on_bar(self, candle, *, close, open, high, low, volume,
                   time, bar_index):
            fast = ta.ema(close, 9)
            slow = ta.ema(close, 21)
            long_cond = ta.crossover(fast, slow)
            if long_cond:
                strategy.entry("L", strategy.long)


    def create_strategy(config):
        return GeneratedStrategy(config or {})

This adapter wraps the polled :class:`Strategy` ABC into Pine's imperative
``strategy.entry / strategy.close / strategy.exit`` semantics: ``on_bar``
runs as Pine intends, and the framework's poll methods
(:meth:`check_long_entry` etc.) read the pending-signal state populated
during ``on_bar``.

A script that plots also imports ``plot`` and ``color``: ``plot()``
records a value per bar for the chart (:meth:`PineStrategy.get_plots`)
and never touches the signal state.

This is a P5.1e MVP — sufficient to instantiate emitted code and feed
basic candles through. Production hardening (full ta/* indicator
coverage, request.security multi-tf delivery, varip tick semantics,
session lifetime hooks) lands in follow-up sprints.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .indicators import EMA, SMA, RSI, ATR
from .models import Candle
from .strategy import Strategy

__all__ = [
    "PineStrategy",
    "ta",
    "math",
    "strategy",
    "request",
    "input",
    "history",
    "nz",
    "na",
    "persistent",
    "plot",
    "color",
]


# ============================================================
# Pending-signal state — populated by strategy.entry/close/exit
# during on_bar, consumed by check_*_entry() afterwards.
# ============================================================

class _SignalState:
    """Per-strategy-instance pending-signal buffer."""

    def __init__(self):
        self.pending_long: Optional[Dict[str, Any]] = None
        self.pending_short: Optional[Dict[str, Any]] = None
        self.pending_close_ids: List[str] = []
        self.long_stop: Optional[float] = None
        self.short_stop: Optional[float] = None
        self.reward_ratio: float = 0.0
        self.leverage: int = 0

    def clear_pending(self):
        self.pending_long = None
        self.pending_short = None
        self.pending_close_ids = []


# ============================================================
# Module-level mutable bag — Pine generated code calls
# `strategy.entry(...)` etc. against a module-style object; the
# PineStrategy.on_bar wrapper binds the active state before
# invoking the subclass's on_bar so the calls land on a real
# instance buffer rather than a global.
# ============================================================

_active_state: Optional[_SignalState] = None
_active_history: Optional["_HistoryBuffer"] = None
_active_persistent: Optional["_PersistentStore"] = None


def _require_active() -> _SignalState:
    if _active_state is None:
        raise RuntimeError(
            "pine_runtime: strategy.* / history / persistent called outside "
            "an active on_bar — this usually means the generated code was "
            "invoked without going through PineStrategy.update()"
        )
    return _active_state


# ============================================================
# Rolling history buffer for `expr[N]` history operator support.
# ============================================================

class _HistoryBuffer:
    """Per-instance rolling cache of named values, capped at HISTORY_CAP bars
    so memory stays bounded. PineStrategy publishes built-in series
    (close/open/high/low/volume/time/bar_index) here at the start of each
    bar; user-emitted code can call history(name, n) to peek backwards."""

    HISTORY_CAP = 512

    def __init__(self):
        self._series: Dict[str, List[Any]] = {}

    def push(self, name: str, value: Any):
        s = self._series.setdefault(name, [])
        s.append(value)
        if len(s) > self.HISTORY_CAP:
            del s[: len(s) - self.HISTORY_CAP]

    def at(self, name: str, n: int):
        s = self._series.get(name)
        if not s:
            return None
        if n < 0 or n >= len(s):
            return None
        return s[-1 - n]


# ============================================================
# var/varip persistence — Pine `var x = expr` evaluates expr
# ONCE on the first bar. We allow generated code to use
# self.var_<name> for the common case; persistent() is the
# escape hatch for runtime-evaluated init expressions.
# ============================================================

class _PersistentStore:
    def __init__(self):
        self._values: Dict[str, Any] = {}

    def get_or_init(self, name: str, init: Callable[[], Any]) -> Any:
        if name not in self._values:
            self._values[name] = init()
        return self._values[name]


# ============================================================
# Per-call-site indicator + cross-state cache.
#
# Pine indicators are stateful: `ta.sma(close, 14)` at line 5 keeps
# accumulating across bars, separate from `ta.sma(close, 14)` at
# line 10. The runtime needs to distinguish call sites and persist
# one indicator instance per (caller_filename, caller_lineno,
# indicator_kind, params) tuple.
#
# We key on the calling frame's filename + lineno via sys._getframe,
# same approach Python's stdlib logging module uses for `Caller`.
# ============================================================

class _IndicatorCache:
    """Per-PineStrategy-instance store mapping call-site identity to
    persistent indicator state (SMA / EMA / RSI / ATR objects, plus
    rolling buffers for highest / lowest, plus prev-bar pairs for
    crossover / crossunder)."""

    def __init__(self):
        self._store: Dict[tuple, Any] = {}

    def get_or_create(self, key: tuple, factory: Callable[[], Any]) -> Any:
        if key not in self._store:
            self._store[key] = factory()
        return self._store[key]

    def get(self, key: tuple, default=None) -> Any:
        return self._store.get(key, default)

    def set(self, key: tuple, value: Any) -> None:
        self._store[key] = value


def _caller_site_key(depth: int = 2) -> tuple:
    """Return (filename, lineno) for the frame `depth` levels up the stack.
    `depth=2` skips this helper + the ta.* shim method, landing on the
    generated-code line that called ta.sma / ta.ema / etc.

    Falls back to a stable but unique sentinel when frame introspection
    fails (some PyPy / Cython embeddings don't provide frames)."""
    import sys
    try:
        f = sys._getframe(depth)
        return (f.f_code.co_filename, f.f_lineno)
    except (ValueError, AttributeError):
        return ("<frameless>", 0)


# ============================================================
# ta / math / strategy / request / input namespace shims.
# These are PLAIN OBJECTS exposed via __all__ — the generated
# Python imports them as if they were submodules.
# ============================================================

_active_indicator_cache: Optional["_IndicatorCache"] = None
_active_candle: Optional[Candle] = None


def _require_indicator_cache() -> "_IndicatorCache":
    if _active_indicator_cache is None:
        raise RuntimeError(
            "pine_runtime: ta.* called outside an active on_bar — the cache "
            "is per-strategy-instance and only valid while a PineStrategy.update "
            "is in flight"
        )
    return _active_indicator_cache


class _TaNamespace:
    """Pine `ta.*` shim with proper per-call-site state persistence.

    Each call site (identified by the caller frame's filename + line number)
    keeps its own indicator instance across bars, so repeated ``ta.sma(close, 14)``
    calls at the same source line accumulate values correctly. Two ``ta.sma(close, 14)``
    calls on different lines are distinct indicators — matching Pine semantics
    where indicator state is tied to the syntactic call site.

    Cross-bar semantics for ``crossover / crossunder`` track the previous-bar
    operand pair per call site, and ``highest / lowest`` keep a rolling window
    of the last N inputs."""

    def sma(self, source: float, length: int) -> float:
        site = _caller_site_key()
        key = ("sma", site, int(length))
        cache = _require_indicator_cache()
        ind = cache.get_or_create(key, lambda: SMA(int(length)))
        ind.update(float(source))
        return ind.get_value() if ind.is_ready() else float("nan")

    def ema(self, source: float, length: int) -> float:
        site = _caller_site_key()
        key = ("ema", site, int(length))
        cache = _require_indicator_cache()
        ind = cache.get_or_create(key, lambda: EMA(int(length)))
        ind.update(float(source))
        return ind.get_value() if ind.is_ready() else float("nan")

    def rsi(self, source: float, length: int) -> float:
        site = _caller_site_key()
        key = ("rsi", site, int(length))
        cache = _require_indicator_cache()
        ind = cache.get_or_create(key, lambda: RSI(int(length)))
        ind.update(float(source))
        return ind.get_value() if ind.is_ready() else float("nan")

    def atr(self, length: int) -> float:
        """Pine ``ta.atr(N)`` returns the N-bar Average True Range. Unlike
        ``ta.sma / ta.ema`` it needs the full Candle (high/low/close), not
        just a single value — we pull the active candle bound by
        PineStrategy.update."""
        if _active_candle is None:
            return float("nan")
        site = _caller_site_key()
        key = ("atr", site, int(length))
        cache = _require_indicator_cache()
        ind = cache.get_or_create(key, lambda: ATR(int(length)))
        ind.update(_active_candle)
        return ind.get_value() if ind.is_ready() else float("nan")

    def crossover(self, a: float, b: float) -> bool:
        """Pine ``ta.crossover(a, b)`` — True only when ``a`` crossed from
        below to above ``b`` on this bar. Requires previous-bar values, so
        we track the (prev_a, prev_b) pair per call site."""
        site = _caller_site_key()
        key = ("crossover_prev", site)
        cache = _require_indicator_cache()
        prev = cache.get(key)
        a_f, b_f = float(a), float(b)
        crossed = (
            prev is not None
            and prev[0] is not None
            and prev[1] is not None
            and prev[0] <= prev[1]
            and a_f > b_f
        )
        cache.set(key, (a_f, b_f))
        return crossed

    def crossunder(self, a: float, b: float) -> bool:
        site = _caller_site_key()
        key = ("crossunder_prev", site)
        cache = _require_indicator_cache()
        prev = cache.get(key)
        a_f, b_f = float(a), float(b)
        crossed = (
            prev is not None
            and prev[0] is not None
            and prev[1] is not None
            and prev[0] >= prev[1]
            and a_f < b_f
        )
        cache.set(key, (a_f, b_f))
        return crossed

    def highest(self, source: float, length: int) -> float:
        """Rolling window max over the last `length` updates."""
        site = _caller_site_key()
        key = ("highest_window", site, int(length))
        cache = _require_indicator_cache()
        window: List[float] = cache.get_or_create(key, lambda: [])
        window.append(float(source))
        if len(window) > int(length):
            del window[: len(window) - int(length)]
        if len(window) < int(length):
            return float("nan")
        import builtins as _b
        return _b.max(window)

    def lowest(self, source: float, length: int) -> float:
        site = _caller_site_key()
        key = ("lowest_window", site, int(length))
        cache = _require_indicator_cache()
        window: List[float] = cache.get_or_create(key, lambda: [])
        window.append(float(source))
        if len(window) > int(length):
            del window[: len(window) - int(length)]
        if len(window) < int(length):
            return float("nan")
        import builtins as _b
        return _b.min(window)

    def change(self, source: float) -> float:
        """Pine ``ta.change(src)`` — current value minus previous bar's
        value at the same call site."""
        site = _caller_site_key()
        key = ("change_prev", site)
        cache = _require_indicator_cache()
        prev = cache.get(key)
        src = float(source)
        cache.set(key, src)
        if prev is None:
            return float("nan")
        return src - prev

    def barssince(self, condition: bool) -> int:
        """Pine ``ta.barssince(cond)`` — bars elapsed since `cond` was last
        True. Returns NaN-sentinel (-1) when cond has never been True."""
        site = _caller_site_key()
        key = ("barssince_state", site)
        cache = _require_indicator_cache()
        state = cache.get(key, -1)
        if condition:
            cache.set(key, 0)
            return 0
        if state < 0:
            return -1
        new_count = state + 1
        cache.set(key, new_count)
        return new_count


class _MathNamespace:
    """Pine `math.*` shim — delegates to Python's builtins."""

    @staticmethod
    def max(*args):
        import builtins
        return builtins.max(*args)

    @staticmethod
    def min(*args):
        import builtins
        return builtins.min(*args)

    @staticmethod
    def abs(x):
        return float(abs(x))

    @staticmethod
    def round(x):
        return float(round(x))

    @staticmethod
    def floor(x):
        import builtins
        return float(builtins.int(x))

    @staticmethod
    def ceil(x):
        import math as _m
        return float(_m.ceil(x))

    @staticmethod
    def sqrt(x):
        import math as _m
        return _m.sqrt(x)


class _StrategyNamespace:
    """Pine `strategy.*` shim — direction constants + entry/close/exit verbs
    that populate the active _SignalState buffer."""

    # Direction constants — Pine generated code uses `strategy.long` /
    # `strategy.short` as opaque sentinels.
    long = "long"
    short = "short"
    percent_of_equity = "percent_of_equity"
    cash = "cash"
    fixed = "fixed"

    @staticmethod
    def entry(id: str, direction: str, qty=None, **kwargs):
        state = _require_active()
        payload = {"id": id, "qty": qty, **kwargs}
        if direction == "long":
            state.pending_long = payload
        elif direction == "short":
            state.pending_short = payload
        else:
            raise ValueError(f"strategy.entry: unknown direction '{direction}'")

    @staticmethod
    def close(id: str, **kwargs):
        state = _require_active()
        state.pending_close_ids.append(id)

    @staticmethod
    def exit(id: str, *, stop=None, limit=None, **kwargs):
        # Pine's strategy.exit registers a take-profit / stop pair for a
        # named entry. MVP just stores the levels on the active state so
        # calculate_*_stop_loss can surface them.
        state = _require_active()
        if stop is not None:
            # Naive: store on whichever side was opened first this bar.
            if state.pending_long is not None or state.long_stop is not None:
                state.long_stop = float(stop)
            if state.pending_short is not None or state.short_stop is not None:
                state.short_stop = float(stop)


class _RequestNamespace:
    """Pine ``request.*`` shim. ``request.security(symbol, tf, expr)`` in
    real Pine pulls a value from a different symbol/timeframe context. The
    engine's multi-tf wiring (P5.1d full) subscribes to additional
    (symbol, timeframe) streams via MarketDataFeed and forwards each
    closed candle into the PineStrategy via ``feed_additional_candle()``.

    The ``expression`` argument is what Pine would compute against the
    higher-tf series — most commonly the bare built-in ``close`` (or
    open/high/low/volume). For MVP we treat it as a hint: when the
    multi-tf cache holds a candle for (symbol, tf), we return the
    corresponding attribute; otherwise fall back to the passed-in value
    so generated code keeps running while the upstream stream warms up."""

    _DEFAULT_ATTR = "close"

    @staticmethod
    def security(symbol: str, timeframe: str, expression, *, attr: Optional[str] = None):
        cached = _read_active_mtf(symbol, timeframe, attr or _RequestNamespace._DEFAULT_ATTR)
        if cached is not None:
            return cached
        return expression


_active_pine_strategy: Optional["PineStrategy"] = None


def _read_active_mtf(symbol: str, timeframe: str, attr: str):
    if _active_pine_strategy is None:
        return None
    return _active_pine_strategy.get_additional_value(symbol, timeframe, attr)


class _InputNamespace:
    """Pine `input.*` shim — pulls values from the strategy config dict,
    fallback to the supplied default. Generated code uses keyword-style
    invocation: input.int(14, "RSI length") etc."""

    @staticmethod
    def int(default, title=None, **kwargs):
        state = _config_for_active()
        if title and title in state:
            return int(state[title])
        return int(default)

    @staticmethod
    def float(default, title=None, **kwargs):
        state = _config_for_active()
        if title and title in state:
            return float(state[title])
        return float(default)

    @staticmethod
    def bool(default, title=None, **kwargs):
        state = _config_for_active()
        if title and title in state:
            return bool(state[title])
        return bool(default)

    @staticmethod
    def string(default, title=None, **kwargs):
        state = _config_for_active()
        if title and title in state:
            return str(state[title])
        return str(default)

    @staticmethod
    def timeframe(default, title=None, **kwargs):
        return _InputNamespace.string(default, title=title, **kwargs)

    @staticmethod
    def source(default, title=None, **kwargs):
        # Source inputs (close/open/high/low) are passed as built-in series
        # references — MVP just echoes the default.
        return default


_active_config: Optional[Mapping[str, Any]] = None


def _config_for_active() -> Mapping[str, Any]:
    return _active_config if _active_config is not None else {}


# ============================================================
# Module-level exports — generated code does
# `from lyrithm_sdk.pine_runtime import ta, math, ...`
# ============================================================

ta = _TaNamespace()
math = _MathNamespace()
strategy = _StrategyNamespace()
request = _RequestNamespace()
input = _InputNamespace()


def history(name: str, n: int):
    """Equivalent of Pine `name[n]` — looks up the value of named series
    `n` bars ago. Returns None when the buffer hasn't filled to that depth
    yet (Pine equivalent: `na`)."""
    if _active_history is None:
        return None
    return _active_history.at(name, int(n))


def nz(value, default=0.0):
    """Pine `nz(x, default)` — return default when value is NaN / None."""
    if value is None:
        return default
    try:
        import math as _m
        if isinstance(value, float) and _m.isnan(value):
            return default
    except Exception:
        pass
    return value


def na(value) -> bool:
    """Pine `na(x)` — True when value is NaN / None."""
    if value is None:
        return True
    try:
        import math as _m
        return isinstance(value, float) and _m.isnan(value)
    except Exception:
        return False


# ============================================================
# plot() and color.* — what the chart draws next to the candles.
# Values are kept per bar on the PineStrategy and read back with
# get_plots(); they never reach the signal state, so a script trades
# the same with or without its plots.
# ============================================================

#: Plots one script may draw; further plot() calls are ignored.
MAX_PLOTS = 16


def _hex_rgb(value: Any) -> Optional[Tuple[int, int, int]]:
    if not isinstance(value, str) or not value.startswith("#") or len(value) not in (7, 9):
        return None
    try:
        return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
    except ValueError:
        return None


def _to_hex(rgb: Tuple[int, int, int], transp: Any = 0) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    try:
        t = float(transp)
    except (TypeError, ValueError):
        t = 0.0
    t = max(0.0, min(100.0, t))
    if t == 0.0:
        return f"#{r:02X}{g:02X}{b:02X}"
    alpha = int(round(255 * (1 - t / 100.0)))
    return f"#{r:02X}{g:02X}{b:02X}{alpha:02X}"


class _ColorNamespace:
    """Pine `color.*` as hex strings: "#RRGGBB", or "#RRGGBBAA" once a
    transparency is applied. The named colours are Pine v5's."""

    aqua = "#00BCD4"
    black = "#363A45"
    blue = "#2196F3"
    fuchsia = "#E040FB"
    gray = "#787B86"
    green = "#4CAF50"
    lime = "#00E676"
    maroon = "#880E4F"
    navy = "#311B92"
    olive = "#808000"
    orange = "#FF9800"
    purple = "#9C27B0"
    red = "#FF5252"
    silver = "#B2B5BE"
    teal = "#00897B"
    white = "#FFFFFF"
    yellow = "#FFEB3B"

    @staticmethod
    def new(color, transp=0):
        """`color.new(c, transp)` — c with 0 (opaque) .. 100 (invisible) transparency."""
        rgb = _hex_rgb(color)
        return color if rgb is None else _to_hex(rgb, transp)

    @staticmethod
    def rgb(red, green, blue, transp=0):
        """`color.rgb(r, g, b, transp)`."""
        return _to_hex((red, green, blue), transp)


color = _ColorNamespace()


def _plot_value(series: Any) -> Optional[float]:
    if isinstance(series, bool) or not isinstance(series, (int, float)):
        return None
    import math as _m
    value = float(series)
    return value if _m.isfinite(value) else None


def plot(series, title=None, color=None, linewidth=1, style=None, **kwargs):
    """Pine `plot()` — draw `series` on the chart. The line is named by
    `title` (untitled plots are "Plot", "Plot 2", ...); `na` leaves a gap.
    Only the value and colour are kept: width, style and the other
    arguments are accepted and ignored. Returns the plot's name."""
    if _active_pine_strategy is None:
        raise RuntimeError("pine_runtime: plot() called outside an active on_bar")
    return _active_pine_strategy._record_plot(_caller_site_key(), series, title, color)


def persistent(name: str, init: Callable[[], Any]):
    """Pine `var name = expr` equivalent for cases where the init expr
    references runtime values (close, candle, etc.) — the generated
    code MVP uses self.var_<name> for compile-time constants instead and
    only falls back to persistent() when the analyzer detects a runtime
    dependency. Kept here so the runtime contract is complete."""
    if _active_persistent is None:
        raise RuntimeError("pine_runtime: persistent() called outside on_bar")
    return _active_persistent.get_or_init(name, init)


# ============================================================
# PineStrategy ABC — generated code subclasses this. Overrides
# update() to bind the active state + invoke on_bar.
# ============================================================

class PineStrategy(Strategy):
    """Adapter bridging Pine's imperative on_bar model into the polled
    Strategy ABC. Generated code overrides :meth:`on_bar` and uses the
    `ta` / `math` / `strategy` / `request` / `input` / `history` / `nz` /
    `na` / `persistent` helpers re-exported by this module."""

    # Subclasses set these via the codegen header.
    PINE_VERSION: int = 5
    STRATEGY_ARGS: Mapping[str, Any] = {}

    def __init__(self, config: Mapping[str, Any]):
        super().__init__()
        self._config: Dict[str, Any] = dict(config or {})
        self._state = _SignalState()
        self._history = _HistoryBuffer()
        self._persistent = _PersistentStore()
        self._indicators = _IndicatorCache()
        # Multi-tf candle cache populated by feed_additional_candle — keyed
        # by (symbol, timeframe) → latest closed Candle. request.security()
        # reads from here on lookup; engine MarketDataFeed wires the feed.
        self._mtf_candles: Dict[tuple, Candle] = {}
        self._last_candle: Optional[Candle] = None
        self._ready_after: int = 1  # default: ready after 1 bar
        self._bar_index = 0
        # plot() call site -> plot name, in the order first plotted.
        self._plot_names: Dict[tuple, str] = {}
        # This bar's plotted values: name -> (value, colour).
        self._plots: Dict[str, Tuple[Optional[float], Optional[str]]] = {}

    # ---- Strategy lifecycle ----
    def update(self, candle: Candle) -> None:
        global _active_state, _active_history, _active_persistent, _active_config
        global _active_indicator_cache, _active_candle
        self._state.clear_pending()
        self._plots = {}
        self._last_candle = candle

        # Publish built-in series into the history buffer so history(name, n)
        # works for past bars.
        self._history.push("close", candle.close)
        self._history.push("open", candle.open)
        self._history.push("high", candle.high)
        self._history.push("low", candle.low)
        self._history.push("volume", candle.volume)
        self._history.push("time", candle.timestamp)
        self._history.push("bar_index", self._bar_index)

        _active_state = self._state
        _active_history = self._history
        _active_persistent = self._persistent
        _active_config = self._config
        _active_indicator_cache = self._indicators
        _active_candle = candle
        global _active_pine_strategy
        _active_pine_strategy = self
        try:
            self.on_bar(
                candle,
                close=candle.close,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                volume=candle.volume,
                time=candle.timestamp,
                bar_index=self._bar_index,
            )
        finally:
            _active_state = None
            _active_history = None
            _active_persistent = None
            _active_config = None
            _active_indicator_cache = None
            _active_candle = None
            _active_pine_strategy = None

        self._bar_index += 1

    # ---- Multi-tf candle delivery (P5.1d engine-side wiring) ----
    def feed_additional_candle(self, symbol: str, timeframe: str, candle: Candle) -> None:
        """Called by the engine (via gRPC UpdateAdditional → strategy-worker-
        python → PineStrategy) to deliver a closed candle from a non-primary
        (symbol, timeframe) stream. The candle is cached for request.security()
        lookups on subsequent bars."""
        self._mtf_candles[(symbol, timeframe)] = candle

    def get_additional_value(self, symbol: str, timeframe: str, attr: str = "close"):
        """Lookup helper used by request.security(). Returns the named
        attribute (close / open / high / low / volume) of the most recently
        delivered candle for (symbol, timeframe), or None when no candle
        has arrived yet."""
        c = self._mtf_candles.get((symbol, timeframe))
        if c is None:
            return None
        return getattr(c, attr, None)

    def is_ready(self) -> bool:
        return self._bar_index >= self._ready_after

    def reset(self) -> None:
        self._state = _SignalState()
        self._history = _HistoryBuffer()
        self._persistent = _PersistentStore()
        self._indicators = _IndicatorCache()
        self._mtf_candles = {}
        self._last_candle = None
        self._bar_index = 0
        self._plot_names = {}
        self._plots = {}

    # ---- plot() ----
    def _record_plot(self, site: tuple, series: Any, title: Any, color: Any) -> Optional[str]:
        name = self._plot_names.get(site)
        if name is None:
            if len(self._plot_names) >= MAX_PLOTS:
                return None
            base = str(title) if title else "Plot"
            taken = set(self._plot_names.values())
            name, n = base, 2
            while name in taken:
                name, n = f"{base} {n}", n + 1
            self._plot_names[site] = name
        self._plots[name] = (_plot_value(series), color if isinstance(color, str) else None)
        return name

    def get_plots(self) -> List[Dict[str, Any]]:
        """This bar's plot() values, in the order the plots first appeared:
        ``{"name", "value", "color"}`` with ``value`` None where the plot
        was `na` or not reached this bar, and ``color`` None for the
        chart's default."""
        out: List[Dict[str, Any]] = []
        for name in self._plot_names.values():
            value, colour = self._plots.get(name, (None, None))
            out.append({"name": name, "value": value, "color": colour})
        return out

    def check_long_entry(self) -> int:
        return 1 if self._state.pending_long is not None else 0

    def check_short_entry(self) -> int:
        return 1 if self._state.pending_short is not None else 0

    def calculate_long_stop_loss(self) -> float:
        if self._state.long_stop is not None:
            return self._state.long_stop
        # Fallback: 1% below entry.
        if self._last_candle is not None:
            return self._last_candle.close * 0.99
        return 0.0

    def calculate_short_stop_loss(self) -> float:
        if self._state.short_stop is not None:
            return self._state.short_stop
        if self._last_candle is not None:
            return self._last_candle.close * 1.01
        return 0.0

    def get_dynamic_reward_ratio(self) -> float:
        if self._state.reward_ratio:
            return self._state.reward_ratio
        # Pull from STRATEGY_ARGS if the buyer baked one in.
        rr = self.STRATEGY_ARGS.get("default_qty_value", 2.0)
        try:
            return float(rr)
        except (TypeError, ValueError):
            return 2.0

    def get_dynamic_leverage(self) -> int:
        if self._state.leverage:
            return self._state.leverage
        return 3

    # ---- Subclass hook ----
    @abstractmethod
    def on_bar(self, candle: Candle, *, close: float, open: float,
               high: float, low: float, volume: float, time: int,
               bar_index: int) -> None:
        """Pine `strategy()` body runs here once per closed candle. Generated
        code injects all top-level Pine statements; the kwargs are the
        Pine built-in series exposed as locals."""
