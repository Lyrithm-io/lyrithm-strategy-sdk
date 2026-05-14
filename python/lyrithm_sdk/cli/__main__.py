# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""`lyrithm` CLI entry point. Defined as a console_script in pyproject.toml."""
from __future__ import annotations

import click

from . import _init, _package, _publish, _test
from .. import __version__


@click.group()
@click.version_option(__version__, prog_name="lyrithm")
def cli() -> None:
    """Lyrithm Strategy SDK — author, test, package, and publish strategies."""


cli.add_command(_init.init)
cli.add_command(_test.test)
cli.add_command(_package.package)
cli.add_command(_publish.publish)


def main() -> None:
    cli(prog_name="lyrithm")


if __name__ == "__main__":
    main()
