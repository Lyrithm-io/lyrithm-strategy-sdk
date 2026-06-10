# Changelog

All notable changes to `lyrithm-strategy-sdk` (Python pip wheel — `Strategy` ABC + indicator library + Pine v5 runtime adapter).

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This repo does not yet ship semver tags — the wheel version is bumped per release-wave alongside `lyrithm-core`. SDK is buyer-facing and **public**; source bytes for buyer-uploaded strategies are not.

Sister-repo changelogs: `lyrithm-core` / `lyrithm-dashboard` / `lyrithm-sandbox` / `lyrithm-mobile` / `lyrithm-personal-release`.

---

## [Unreleased] — Phase C launch wave

4 commits ahead of `main`'s last pushed state, queued for the next deploy wave.

### Added — P5.1e Pine runtime adapter (commits `677a9a0` MVP + `7ddff34` full-pass, 2026-06-10)

Bridges Pine v5 transpiled strategies (emitted by `lyrithm-core`'s `PineToPythonCodegen`) to the polled `Strategy` ABC. The codegen targets this adapter; users never import it directly.

- **`PineStrategy` ABC** — wraps Pine imperative `on_bar` / `strategy.entry` / `strategy.close` into the polled `Strategy.update()` contract. `_active_candle` module global is bound by `PineStrategy.update` so `ta.atr` can read the current candle without threading it through every signature.
- **`_IndicatorCache`** per-instance store mapping call-site identity (`sys._getframe`-derived `filename:lineno`) to persistent indicator state — so two `ta.sma(close, 14)` calls on different lines are distinct indicators per Pine semantics, and a single `ta.sma` call persists across bars without re-initialising.
- **`ta.*` namespace** — `sma` / `ema` (Wilder seed) / `rsi` / `atr` (uses active candle, bound by PineStrategy.update — no longer returns NaN as in MVP) / `crossover` / `crossunder` (proper prev-bar tracking; true only on transition bar) / `highest` / `lowest` (rolling window buffers) / `change` (bar-over-bar delta) / `barssince` (bars-since-cond counter with -1 sentinel).
- **`history`** — 512-bar rolling buffer; `history("close", n)` returns close n bars ago, NaN if not enough history.
- **`request.security(symbol, tf, expression, *, attr="close")`** — multi-timeframe data resolution. Returns cached field if `feed_additional_candle(symbol, tf, candle)` has been called (by `strategy-worker-python`'s `OnAdditionalCandle` handler); falls back to the in-line `expression` on miss so the generated code keeps running while the upstream stream warms up.
- **`PineStrategy.feed_additional_candle(symbol, tf, candle)`** — called by `strategy-worker-python`'s `OnAdditionalCandle` RPC handler; caches in `_mtf_candles` dict.
- **`PineStrategy.reset()`** — clears multi-tf cache + indicator cache for clean hot-reload.
- **`strategy` / `input` / `math` namespaces** — `strategy.entry/close/exit_short`, `input.float/int/string/bool` (resolved at upload-time + wired into instance config), `math.{min,max,abs,...}` proxies.
- **`nz` / `na` helpers** — Pine null-handling shims (`nz(x, default)` returns x unless NaN).
- **Tests — 16 Pine semantics replay cases** (`test_pine_semantics_replay.py`) substitute for TradingView reference parity (closed platform — can't programmatically drive). Hand-computed expected outputs for: `sma` NaN-until-fill + persistence + distinct-per-call-site, `ema` Wilder seed, `crossover` transition-bar-only + reset-after-recross, `highest` / `lowest` rolling window, `change` diff, `barssince` -1+reset+count, `history` N-back, `atr` Wilder smoothing, `request.security` pre/post-feed fallback. `test_pine_runtime.py` updated (`test_ta_outside_on_bar_raises_runtime_error` replaces obsolete `test_ta_sma_proxies_to_indicator_value`). Total pytest **50 cases green**.

### Added — P4.2 bundled reference strategies (commit `5d4215f`, 2026-06-05)

3 new strategies under `python/examples/` — each ships `strategy.py` + `lyrithm.yaml` + `config_schema.json` + 4-bar `_MIN_WARMUP_BARS` guard. Tests `test_p42_examples.py` 16 cases. SDK total **36 → 52** (+16).

- **`rsi-mean-reversion`** — classic RSI bounded reversion w/ adjustable upper/lower thresholds.
- **`donchian-breakout`** — Donchian channel breakout w/ N-period high/low window.
- **`macd-divergence`** — MACD line + signal + histogram divergence detection.

### Added — P4.1 promote sandbox extensions into SDK canonical (commit `190c81e`, 2026-06-05)

`atr.py` rewrite (sandbox `_has_prev` first-candle anchor + back-compat `import_state` branch for v1.1.0 persisted state) + `market_regime.py` rewrite (directional 1-arg mode + UPTREND / DOWNTREND regimes + internal ADX driver + `get_regime()` alias). SDK indicator tests **13 → 19** (+6). `lyrithm-sandbox`'s `CANONICAL_FILES` parity gate now byte-syncs from these SDK files — sandbox tracks SDK as source of truth.

---

## [Pre-tag history] — pushed commits

- `db1d8be` — **Lyrid γ · Bollinger Mean-Reversion (Sulafat)** open example (2026-05~06)
- `90eb29e` — **S4** SMA indicator + `sma-crossover` example (bundled Day 1 strategy for Personal Edition)
- `7b13554` — `fix(cli)` include entrypoint in publish metadata + handle camelCase status
- `5af322f` — SDK init + vegas-core Phase 1.0 + 1.2 Wave A
- `133d03a` — initial commit
