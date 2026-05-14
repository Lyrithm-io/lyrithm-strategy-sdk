# lyrithm-sdk (Python)

```bash
pip install lyrithm-sdk
```

See the top-level repo [README](../README.md) and [docs/](../docs/) for full reference.

Layout:

```
python/
├── lyrithm_sdk/
│   ├── __init__.py
│   ├── strategy.py        Strategy ABC + lifecycle contract
│   ├── models.py          Candle, Signal, TradeResult
│   ├── manifest.py        lyrithm.yaml parser + validator
│   ├── testing.py         BacktestRunner (local harness, no cloud)
│   ├── indicators/        EMA, ADX, ATR, MarketRegime
│   └── cli/               lyrithm init|test|package|publish
├── examples/
│   └── ema-cross/         Minimal long/short crossover strategy
└── tests/
```
