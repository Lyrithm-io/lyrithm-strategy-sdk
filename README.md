# Lyrithm Strategy SDK

Build, test, and publish trading strategies for the [Lyrithm](https://lyrithm.com) platform.

The SDK gives strategy creators a clean Python API (Java and Pine coming) plus a `lyrithm` CLI for scaffolding, local backtesting, packaging, and publishing to the Lyrithm cloud.

## Status

| Language | Status         | Package          |
|----------|----------------|------------------|
| Python   | Phase 1 (alpha)| `lyrithm-sdk`    |
| Java     | Phase 2 (planned) | `com.lyrithm:lyrithm-strategy-sdk` |
| Pine     | Phase 3 (planned) | n/a (transpiled) |

## Install (Python)

```bash
pip install lyrithm-sdk
```

Requires Python 3.10+.

## Quick start

```bash
lyrithm init my-strategy
cd my-strategy
# edit strategy.py
lyrithm test --csv data/btc-1h.csv
lyrithm package
lyrithm publish --api https://api.lyrithm.com
```

A complete walkthrough lives in [docs/quickstart.md](docs/quickstart.md).

## Strategy shape

A Lyrithm strategy is a single `.py` file (Python), a single `.java` file (Java, planned), or `.pine` (planned), plus a `lyrithm.yaml` manifest and `config_schema.json` describing tunable parameters.

```python
from lyrithm_sdk import Strategy, Candle, Signal
from lyrithm_sdk.indicators import EMA


class EmaCross(Strategy):
    def __init__(self, config):
        self.fast = EMA(config["ema_fast"])
        self.slow = EMA(config["ema_slow"])
        self.prev_diff = None

    def update(self, candle: Candle) -> None:
        self.fast.update(candle.close)
        self.slow.update(candle.close)

    def is_ready(self) -> bool:
        return self.fast.is_ready() and self.slow.is_ready()

    def check_long_entry(self) -> int:
        diff = self.fast.get_value() - self.slow.get_value()
        if self.prev_diff is not None and self.prev_diff <= 0 < diff:
            self.prev_diff = diff
            return 1
        self.prev_diff = diff
        return 0

    def check_short_entry(self) -> int:
        diff = self.fast.get_value() - self.slow.get_value()
        if self.prev_diff is not None and self.prev_diff >= 0 > diff:
            return 1
        return 0

    def calculate_long_stop_loss(self) -> float: ...
    def calculate_short_stop_loss(self) -> float: ...
    def get_dynamic_reward_ratio(self) -> float: return 2.0
    def get_dynamic_leverage(self) -> int: return 5
    def reset(self) -> None: ...
```

Full interface: [docs/strategy-spec.md](docs/strategy-spec.md).
Manifest reference: [docs/lyrithm-yaml-reference.md](docs/lyrithm-yaml-reference.md).

## Versioning

What counts as the public API, the semver policy (pre-1.0 semantics, deprecation
window), and the 1.0.0 promotion criteria are defined in [VERSIONING.md](VERSIONING.md).
The Java contract jar `com.lyrithm:lyrithm-strategy-api` is covered by the same document.

## Repo layout

```
lyrithm-strategy-sdk/
├── LICENSE                Apache License 2.0
├── NOTICE
├── README.md              (this file)
├── python/
│   ├── lyrithm_sdk/       SDK package — Strategy, indicators, models, CLI
│   ├── examples/          Reference strategies (ema-cross)
│   ├── tests/
│   └── pyproject.toml
├── java/                  Phase 2 — Maven artifact
├── pine/                  Phase 3 — Pine v5 subset transpiler
└── docs/
    ├── quickstart.md
    ├── strategy-spec.md
    └── lyrithm-yaml-reference.md
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

Strategies authored *using* this SDK are **your own work** and remain under whatever license you choose. The SDK's Apache 2.0 license does not transfer to your strategy code.
