# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""`lyrithm test` — run the local BacktestRunner against a CSV file."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping

import click

from ..manifest import load_manifest
from ..strategy import Strategy
from ..testing import BacktestRunner, load_candles_csv


def _import_strategy_module(entrypoint: Path):
    spec = importlib.util.spec_from_file_location(f"_lyrithm_user_{entrypoint.stem}", entrypoint)
    if spec is None or spec.loader is None:
        raise click.ClickException(f"cannot load {entrypoint}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_strategy(module, config: Mapping[str, Any]) -> Strategy:
    factory = getattr(module, "create_strategy", None)
    if callable(factory):
        instance = factory(config)
        if not isinstance(instance, Strategy):
            raise click.ClickException("create_strategy() did not return a Strategy instance")
        return instance

    candidates = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy
    ]
    if not candidates:
        raise click.ClickException(
            "module exposes neither create_strategy(config) nor a Strategy subclass"
        )
    if len(candidates) > 1:
        names = ", ".join(c.__name__ for c in candidates)
        raise click.ClickException(
            f"module exposes multiple Strategy subclasses ({names}); define create_strategy() to disambiguate"
        )
    cls = candidates[0]
    try:
        return cls(config)
    except TypeError:
        return cls()


@click.command()
@click.option(
    "--project",
    "project_dir",
    default=".",
    help="Strategy project directory (contains lyrithm.yaml). Defaults to cwd.",
)
@click.option(
    "--csv",
    "csv_path",
    required=True,
    help="OHLCV CSV file with columns: timestamp,open,high,low,close,volume.",
)
@click.option("--limit", default=0, type=int, help="Optional cap on number of candles to feed.")
def test(project_dir: str, csv_path: str, limit: int) -> None:
    """Run a strategy against a CSV of candles and print all signals it produces."""
    project = Path(project_dir).resolve()
    manifest = load_manifest(project / "lyrithm.yaml")

    if manifest.language != "python":
        raise click.ClickException(
            f"lyrithm test (Python) cannot run a {manifest.language} strategy; "
            "Java and Pine support arrives in later phases"
        )

    entrypoint = project / manifest.entrypoint
    if not entrypoint.exists():
        raise click.ClickException(f"entrypoint not found: {entrypoint}")

    module = _import_strategy_module(entrypoint)
    strategy = _resolve_strategy(module, manifest.default_config)

    candles = load_candles_csv(Path(csv_path))
    if limit > 0:
        candles = candles[:limit]

    runner = BacktestRunner(strategy)
    report = runner.run(candles)

    click.echo(f"strategy: {manifest.name} v{manifest.version}")
    click.echo(report.summary())
    if report.signals:
        click.echo("first 10 signals:")
        for s in report.signals[:10]:
            click.echo(
                f"  ts={s.timestamp}  {s.side.value:5s}  rule={s.rule_id}  "
                f"price={s.price:.4f}  sl={s.stop_loss:.4f}  "
                f"rr={s.reward_ratio:.2f}  lev={s.leverage}  riskx={s.risk_multiplier:.2f}"
            )
