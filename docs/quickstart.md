# Quickstart

End-to-end walkthrough: from blank machine to a strategy running on the Lyrithm platform.

## 1. Install

```bash
python -m pip install --upgrade pip
pip install lyrithm-sdk
lyrithm --version
```

Requires Python 3.10+.

## 2. Scaffold

```bash
lyrithm init my-first-strategy
cd my-first-strategy
ls
# lyrithm.yaml  strategy.py  config_schema.json  README.md
```

`strategy.py` ships as a working EMA-cross stub — open it, change as you like.

## 3. Test locally

Grab a CSV of OHLCV candles (Binance Vision public dumps are easiest) and point the harness at it:

```bash
lyrithm test --csv ~/data/btc-1h.csv
# strategy: my-first-strategy v0.1.0
# candles_processed=8760  signals=42 (long=21, short=21)
# first 10 signals:
#   ts=1716489600000  long   rule=1  price=66421.7  sl=65240.1  rr=2.00  lev=5  riskx=1.00
#   ...
```

The harness uses the same `Strategy` ABC the production runtime uses, so what you see locally is what the platform will see.

## 4. Validate the package

```bash
lyrithm package
# Packaged 4 files → my-first-strategy-0.1.0.lyrithm.zip
#   sha256: ...
```

`package` confirms the manifest parses, the entrypoint exists, the JSON Schema is valid, and bundles everything into a single artifact you can inspect before publishing.

## 5. Publish

```bash
export LYRITHM_API=http://127.0.0.1:8080
export LYRITHM_API_TOKEN=...   # Phase 2: Clerk-issued JWT
lyrithm publish --dry-run      # show what would be sent
lyrithm publish                # actually upload
# Published. template_id=...  status=pending_review
```

Phase 1: uploads land in `pending_review` and are admin-approved before activation. Phase 2: automated bandit + AST scan plus manual review queue.

## 6. Run a live instance

Once approved you create per-account instances against the template via the Lyrithm dashboard (or `POST /api/v1/instances`). Each instance can override individual fields of `default_config` without touching the source.

## What's next

- [strategy-spec.md](strategy-spec.md) — every method on the `Strategy` ABC explained.
- [lyrithm-yaml-reference.md](lyrithm-yaml-reference.md) — full manifest field reference.
- `python/examples/ema-cross/` — minimal worked example covering every required method.
