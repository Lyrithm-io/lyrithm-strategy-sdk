# SMA Crossover — Day 1 Lyrithm Personal Edition strategy

The simplest viable trend-following strategy bundled with Lyrithm
Personal Edition. Buy when the fast SMA crosses above the slow SMA, sell
when it crosses below, with an ATR-multiple stop loss.

## Why this is your Day 1

A new buyer who runs `docker compose up` should be able to start paper
trading the same day. SMA crossover is the canonical entry-level
strategy taught in every intro trading book — boring, well understood,
no surprises. Fork it, tune the periods, then move on to the more
sophisticated bundled `ema-cross` or the closed-source `vegas-adx`.

## Defaults

| Parameter | Default | Notes |
| --- | --- | --- |
| `sma_fast` | 20 | Tune lower (10–14) for faster signals, higher (30+) for fewer false triggers |
| `sma_slow` | 50 | Standard trend filter; some traders prefer 100 or 200 |
| `atr_period` | 14 | Wilder's default — leave it |
| `stop_atr_mult` | 2.0 | Wider than ema-cross (1.5) because SMA lag means the noise envelope is bigger |
| `reward_ratio` | 2.0 | Take profit at 2× the stop-loss distance |
| `leverage` | 5 | Conservative; raise carefully and never above what you'd accept losing twice |

## Run locally

```bash
# From the SDK repo root:
python -m lyrithm_sdk test examples/sma-crossover \
  --candles examples/data/btc-1h-30d.csv
```

See the [Lyrithm Strategy SDK README](../../README.md) for the full
toolchain (`test`, `package`, `publish`).
