# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
from __future__ import annotations

from pathlib import Path

import pytest

from lyrithm_sdk.manifest import ManifestError, load_manifest


def _write(tmp: Path, body: str) -> Path:
    p = tmp / "lyrithm.yaml"
    p.write_text(body, encoding="utf-8")
    return p


_VALID = """\
name: my-strategy
display_name: "My Strategy"
language: python
entrypoint: strategy.py
version: 0.1.0
source_visibility: closed
default_config:
  ema_fast: 12
"""


def test_load_valid_manifest(tmp_path):
    m = load_manifest(_write(tmp_path, _VALID))
    assert m.name == "my-strategy"
    assert m.language == "python"
    assert m.entrypoint == "strategy.py"
    assert m.version == "0.1.0"
    assert m.is_open_source is False
    assert m.default_config == {"ema_fast": 12}


def test_missing_required_field_raises(tmp_path):
    with pytest.raises(ManifestError, match="missing required field"):
        load_manifest(_write(tmp_path, "name: x\n"))


def test_invalid_name_rejected(tmp_path):
    body = _VALID.replace("my-strategy", "MyStrategy")
    with pytest.raises(ManifestError, match="invalid name"):
        load_manifest(_write(tmp_path, body))


def test_invalid_language_rejected(tmp_path):
    body = _VALID.replace("python", "ruby")
    with pytest.raises(ManifestError, match="invalid language"):
        load_manifest(_write(tmp_path, body))


def test_invalid_version_rejected(tmp_path):
    body = _VALID.replace("0.1.0", "v1")
    with pytest.raises(ManifestError, match="invalid version"):
        load_manifest(_write(tmp_path, body))


def test_entrypoint_must_be_filename(tmp_path):
    body = _VALID.replace("strategy.py", "../strategy.py")
    with pytest.raises(ManifestError, match="entrypoint"):
        load_manifest(_write(tmp_path, body))


def test_invalid_visibility_rejected(tmp_path):
    body = _VALID.replace("closed", "secret")
    with pytest.raises(ManifestError, match="source_visibility"):
        load_manifest(_write(tmp_path, body))
