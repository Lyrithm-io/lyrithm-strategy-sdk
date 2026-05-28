# Lyrid γ · Bollinger Mean-Reversion (Sulafat)

> γ Lyrae · Sulafat — the steady anchor at the parallelogram base of Lyra.
> γ rides the same theme: only trade when price oscillates around its
> long-term anchor, never when it's running.

Open-source, long-only mean-reversion strategy. Bundled as the reference
example for the **Lyrid γ** lineage and runnable on both:

- **Lyrithm Cloud** — subscribe to the strategy from `/dashboard/observatory`
- **Lyrithm Personal Edition** — comes bundled in the engine image; appears
  in your local strategy picker out of the box

## At a glance

| Aspect | Value |
|---|---|
| Side | Long-only (short check returns 0 by design) |
| Edge | Mean reversion in range-bound regime |
| Entry filter | BB-lower tag + RSI oversold + trend buffer + range band |
| Exit | Fixed % stop / take-profit (R:R defaults to 2.0) |
| Best regime | Sideways / consolidating |
| Worst regime | Strong downtrend (filter mitigates but does not eliminate) |
| Indicators | BollingerBands(20, 2.0) · RSI(14) · EMA(100) |

## Entry rules (all four must hold)

| # | Rule | Defaults |
|---|---|---|
| 1 | Touch — `low ≤ BB_lower` | BB(20, σ=2.0) |
| 2 | Stretch — `RSI(14) < rsi_oversold` | RSI < 40 |
| 3 | Trend floor — `close > EMA(long) × trend_buffer` | EMA(100) × 0.95 |
| 4 | Range regime — `|close − EMA(long)| / EMA(long) < range_band_pct` | < 8% |

Rule 4 is the keystone: it suppresses the strategy entirely during strong
trends, where the BB-tag-and-bounce signal degrades. The strategy
intentionally trades less than a naive BB-mean-reverter and accepts
lower fill frequency in exchange for higher win-rate stability.

## Risk

- Stop = `entry × (1 − stop_loss_pct)` — defaults to 2.5%
- Take-profit = stop × `R:R` where `R:R = take_profit_pct / stop_loss_pct`
  — defaults give R:R = 2.0
- Leverage and percent-of-equity sizing handled by the platform's sizer

The two-knob (SL%, TP%) design is intentional: traders think in percent
of price, not in ratios. The R:R falls out of the pair.

## Default config

```yaml
bb_length: 20
bb_stdev: 2.0
rsi_period: 14
rsi_oversold: 40
ema_length: 100
trend_buffer: 0.95
range_band_pct: 0.08
stop_loss_pct: 0.025
take_profit_pct: 0.05
leverage: 5
```

All values match the original Pine-script reference the strategy was
ported from. Every field is tunable from the dashboard form.

## Run locally

```bash
pip install -e .                         # from lyrithm-strategy-sdk root
cd python/examples/gamma-bb-mr
lyrithm test --csv ~/data/btc-1h.csv     # the SDK harness
```

## Lineage

The Lyrid scheme names each strategy family after a star in the
constellation Lyra:

| Slot | Star | Theme | Status |
|---|---|---|---|
| α | Vega | Closed-source flagship execution | ACTIVE — `vegas-adx` |
| β | Sheliak (eclipsing binary) | Paired / spread trading | Reserved |
| **γ** | **Sulafat (steady anchor)** | **Mean reversion** | **`gamma-bb-mr` — this strategy** |
| δ | RR Lyrae (prototype variable) | Volatility / regime-switching | Reserved |
| ε | Aladfar (double-double) | Hedged / multi-leg execution | Reserved |

Fork this strategy as a starting point for any γ-lineage variant —
Donchian-channel mean-reversion, Keltner-channel mean-reversion, or
your own band construction.

## License

Apache 2.0 (covered by the SDK repo's root `LICENSE`).
