# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""`lyrithm package` — validate the manifest and bundle the project into a .lyrithm.zip."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import click

from ..manifest import load_manifest

_INCLUDED_GLOBS = ("lyrithm.yaml", "*.py", "*.json", "README.md", "README.rst")
_EXCLUDED_DIRS = {"__pycache__", ".git", ".venv", "venv", ".pytest_cache", ".mypy_cache"}


def _collect_files(project: Path) -> list[Path]:
    files: list[Path] = []
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIRS for part in path.relative_to(project).parts):
            continue
        if any(path.match(g) for g in _INCLUDED_GLOBS):
            files.append(path)
    return sorted(files)


@click.command()
@click.option(
    "--project",
    "project_dir",
    default=".",
    help="Strategy project directory. Defaults to cwd.",
)
@click.option(
    "--out",
    "out_path",
    default=None,
    help="Output .lyrithm.zip path. Defaults to ./<name>-<version>.lyrithm.zip.",
)
def package(project_dir: str, out_path: str | None) -> None:
    """Validate the project and bundle it into a deployable .lyrithm.zip artifact."""
    project = Path(project_dir).resolve()
    manifest = load_manifest(project / "lyrithm.yaml")

    entrypoint = project / manifest.entrypoint
    if not entrypoint.exists():
        raise click.ClickException(f"entrypoint not found: {entrypoint}")

    manifest.load_config_schema(project)

    files = _collect_files(project)
    if not files:
        raise click.ClickException("no files matched the package globs")

    out = Path(out_path) if out_path else Path.cwd() / f"{manifest.name}-{manifest.version}.lyrithm.zip"

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.relative_to(project).as_posix())

    sha256 = hashlib.sha256(out.read_bytes()).hexdigest()
    click.echo(f"Packaged {len(files)} files → {out}")
    click.echo(f"  sha256: {sha256}")
    click.echo(f"  name:   {manifest.name}")
    click.echo(f"  version:{manifest.version}")
    click.echo(f"  language:{manifest.language}")
    click.echo(f"  visibility:{manifest.source_visibility}")
