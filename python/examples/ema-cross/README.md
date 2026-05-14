# EMA Cross — minimal example

A trivial trend-following strategy: go long when the fast EMA crosses above the slow EMA, short when it crosses below. Stop loss is `close ± ATR(14) × stop_atr_mult`.

Read [strategy.py](strategy.py) — every method on the `Strategy` ABC is implemented and nothing else. This is the shortest path to "my own strategy runs on the platform".

## Try locally

```bash
lyrithm test --project python/examples/ema-cross --csv path/to/btc-1h.csv
```

## Open source

`lyrithm.yaml` marks `source_visibility: open`, so other users on the platform can fork it as a starting template.
