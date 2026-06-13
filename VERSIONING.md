# Versioning & public API contract

This document defines what "the Lyrithm strategy API" is, which parts of it carry a
compatibility promise, and how versions move. It governs two artifacts:

| Artifact | Where | Current |
|---|---|---|
| `lyrithm-sdk` (Python wheel) | this repo, `python/` | 0.1.0 |
| `com.lyrithm:lyrithm-strategy-api` (Java contract jar) | `lyrithm-core/lyrithm-strategy-api`, consumed by engine + lyrithm-sandbox | 0.1.0 |

The `version:` field inside a strategy author's `lyrithm.yaml` is the **author's own
strategy version** — it must be semver-shaped, but is otherwise not governed here.

The wheel version is single-sourced from `lyrithm_sdk.__version__`
(`python/lyrithm_sdk/__init__.py`); `pyproject.toml` reads it via hatchling's dynamic
version. Bump it in exactly one place.

---

## 1. The public surface

These are covered by the compatibility promise. If it isn't listed here (or is
underscore-prefixed), it can change in any release without notice.

### 1.1 Python import surface

```python
from lyrithm_sdk import Strategy, Candle, Signal, SignalSide, TradeResult  # + __version__
from lyrithm_sdk.indicators import EMA, SMA, ADX, ATR, BollingerBands, RSI, MarketRegime, Regime
from lyrithm_sdk.testing import BacktestRunner, BacktestReport, SignalRecord, load_candles_csv
from lyrithm_sdk.manifest import Manifest, ManifestError, load_manifest
```

### 1.2 The `Strategy` contract

The polled lifecycle defined in `python/lyrithm_sdk/strategy.py`:

- **Abstract** (every strategy must implement): `update`, `is_ready`, `reset`,
  `check_long_entry`, `check_short_entry`, `calculate_long_stop_loss`,
  `calculate_short_stop_loss`, `get_dynamic_reward_ratio`, `get_dynamic_leverage`.
- **Optional hooks** (defaults provided, signatures frozen): `get_dynamic_risk_multiplier`,
  `get_adx`, `get_market_regime`, `on_trade_close`, `on_destroy`, `export_state`,
  `import_state`.
- **Loader discovery rules**: a module exposes `create_strategy(config)` **or** exactly one
  top-level `Strategy` subclass with a `(config)` or no-arg constructor.

This contract is mirrored 1:1 by Java `com.lyrithm.strategy.api.Strategy`. A change here
is a contract change in **both** artifacts and they bump together.

### 1.3 CLI

`lyrithm init | test | package | publish` — command names, documented flags, and exit
codes. Human-readable output formatting is *not* covered; do not parse it.

### 1.4 On-disk formats

- `lyrithm.yaml` manifest schema — [docs/lyrithm-yaml-reference.md](docs/lyrithm-yaml-reference.md)
- `config_schema.json` parameter-schema contract — [docs/strategy-spec.md](docs/strategy-spec.md)
- the `.lyrithm.zip` package layout produced by `lyrithm package`

### 1.5 Behavioral surfaces (easy to miss)

- **Indicator numeric output.** The bundled indicators are the shared numeric reference
  for lyrithm-core and lyrithm-sandbox (sandbox byte-syncs its `CANONICAL_FILES` from
  these sources). A change to an indicator's numeric output for the same input stream is
  a **breaking change**, even if no signature moved.
- **Persisted state shape.** Dicts written by `export_state` (strategy and bundled
  indicators) must remain readable by `import_state` across at least one minor upgrade —
  hot-reload and crash-replay restore state written by the previous version. Precedent:
  `indicators/atr.py` keeps a back-compat branch for v1.1.0-era persisted state.

### 1.6 Explicitly NOT public

- `lyrithm_sdk.pine_runtime` — codegen target for lyrithm-core's `PineToPythonCodegen`.
  Strategy authors never import it; it moves with the codegen in any release.
- `lyrithm_sdk.cli._*` modules and all underscore-prefixed names.
- Indicator internals (buffer layouts, warm-up bookkeeping) beyond §1.5.

---

## 2. Semver policy

### Pre-1.0 (now): `0.MINOR.PATCH`

- **PATCH** — bug fixes and strictly additive changes only. Never breaks §1. Always safe
  to upgrade.
- **MINOR** — may contain breaking changes to §1. Every break must be listed in
  [CHANGELOG.md](CHANGELOG.md) under a **Breaking** heading with a migration note.
- The wheel is bumped per release wave alongside `lyrithm-core` (engine, sandbox, and SDK
  move in lockstep; there is no independent SDK release train before 1.0).

### Deprecation

Deprecate in minor `N` (runtime `DeprecationWarning` + CHANGELOG entry), remove no
earlier than minor `N+2` or 1.0.0, whichever comes first.

### The Java jar

`lyrithm-strategy-api` versions track the **contract** (§1.2), not the release wave — it
bumps only when the contract surface changes, and then in lockstep with the SDK minor
that ships the same change. Its protobuf/gRPC dependency pins move in lockstep across
lyrithm-core + lyrithm-sandbox (see the pom note) to avoid wire-format drift; a
pin-only bump is a PATCH.

### 1.0.0 criteria

Both artifacts promote to 1.0.0 together when all of:

1. third-party strategy upload is open publicly (sandbox / Cloud GA),
2. the `Strategy` contract and `lyrithm.yaml` schema have survived one full release wave
   with no breaking change,
3. the Java authoring story (Phase 2) is decided — whether Java authors consume
   `lyrithm-strategy-api` directly or a separate `lyrithm-strategy-sdk` artifact.

After 1.0.0, standard semver: breaking changes require a MAJOR bump, and the pre-1.0
"breaking allowed in MINOR" clause above is dead.
