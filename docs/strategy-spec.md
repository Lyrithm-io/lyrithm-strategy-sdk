# Strategy spec

A Lyrithm strategy implements the `Strategy` ABC. The same shape exists in every supported language (Python today; Java and Pine planned).

## Lifecycle

```
                    ┌──────────────┐
                    │ __init__(cfg)│   resolved config dict (template default
                    └──────┬───────┘   merged with user override)
                           ▼
              ┌────── update(candle) ──────┐   one closed candle at a time
              │                            │   may be called millions of times
              │   is_ready() == True ──────┘
              │           │
              │           ▼
              │   check_long_entry()  → 0 | 1..n  (rule id that fired)
              │   check_short_entry() → 0 | 1..n
              │           │
              │           ▼  (on signal)
              │   calculate_long_stop_loss() / calculate_short_stop_loss()
              │   get_dynamic_reward_ratio()
              │   get_dynamic_leverage()
              │   get_dynamic_risk_multiplier()
              │
              │   on_trade_close(result) ← platform calls back after each
              │                              trade closes (for stateful sizers)
              │
              └─ reset() / on_destroy() at instance teardown
```

## Required methods

| Method | Return | Purpose |
|---|---|---|
| `update(candle: Candle)` | None | Feed one closed OHLCV candle. Update indicators + internal state here. |
| `is_ready()` | bool | True once enough candles have been seen to produce signals. |
| `reset()` | None | Restore all internal state to a fresh post-construction state. |
| `check_long_entry()` | int | `0` = no signal. `>0` = rule id that fired (free-form). |
| `check_short_entry()` | int | Same shape as `check_long_entry`. |
| `calculate_long_stop_loss()` | float | Absolute price level for stop on a long entry. |
| `calculate_short_stop_loss()` | float | Absolute price level for stop on a short entry. |
| `get_dynamic_reward_ratio()` | float | Reward/risk ratio for position sizing. Return a constant if not dynamic. |
| `get_dynamic_leverage()` | int | Leverage to request from the exchange. |

## Optional methods (sensible defaults)

| Method | Default | Override when |
|---|---|---|
| `get_dynamic_risk_multiplier()` | `1.0` | Return >1.0 from high-conviction zones to scale position size beyond the baseline sizer output. |
| `get_adx()` / `get_market_regime()` | `0.0` / `"N/A"` | Surface diagnostics to the dashboard. |
| `on_trade_close(result: TradeResult)` | no-op | Maintain stateful sizers (e.g. anti-martingale). |
| `on_destroy()` | no-op | Release resources before instance teardown. |
| `export_state()` / `import_state(state)` | empty / no-op | Persist state across hot-reloads and crashes. |

## Entry-point convention

The platform loader prefers a `create_strategy(config)` factory and falls back to a single top-level `Strategy` subclass:

```python
def create_strategy(config: Mapping[str, Any]) -> Strategy:
    return MyStrategy(config or {})
```

If the module exposes multiple `Strategy` subclasses, define `create_strategy` to disambiguate. Otherwise the loader errors.

## State persistence

`export_state()` and `import_state()` are how strategies survive **hot-reloads** (config change) and **crash recovery** (process restart). Return any JSON-safe dict. The platform stores it alongside the instance row in the database.

Stateless strategies can skip these — the defaults return `{}` and no-op.

## Threading and isolation

You may assume **single-threaded** invocation per instance. The platform creates one strategy object per user-instance and serializes all calls to it. You do **not** need locks inside the strategy.

Different instances of the same template run in **separate strategy objects** (and Phase 1.4+ in separate Docker containers), so cross-tenant state cannot leak.
