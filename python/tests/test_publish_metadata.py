# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""Wire-contract tests for the multipart metadata sent by `lyrithm publish`.

These guard against a class of bug that only the live backend would catch
otherwise: silently dropping a field required by the vegas-core
TemplateUploadMetadata DTO. Keep REQUIRED_METADATA_FIELDS aligned with
TemplateUploadMetadata.java + TemplateService.validateUpload."""
from __future__ import annotations

from pathlib import Path

from lyrithm_sdk.cli._publish import REQUIRED_METADATA_FIELDS, build_metadata
from lyrithm_sdk.manifest import load_manifest


def _write_manifest(tmp_path: Path) -> Path:
    body = """
name: cli-test
display_name: "CLI Test"
language: python
entrypoint: strategy.py
version: 0.1.0
description: "scaffolded"
tags: [example]
source_visibility: closed
default_config:
  ema_fast: 12
"""
    p = tmp_path / "lyrithm.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_metadata_includes_all_backend_required_fields(tmp_path: Path):
    manifest = load_manifest(_write_manifest(tmp_path))
    meta = build_metadata(manifest, {"title": "schema"})
    missing = REQUIRED_METADATA_FIELDS - set(meta)
    assert missing == set(), f"backend will 400; metadata missing: {sorted(missing)}"


def test_metadata_carries_manifest_entrypoint(tmp_path: Path):
    # Direct regression for the 2026-05-14 bug where build_metadata
    # silently dropped `entrypoint` and live publish returned 400
    # "entrypoint is required".
    manifest = load_manifest(_write_manifest(tmp_path))
    meta = build_metadata(manifest, {})
    assert meta["entrypoint"] == "strategy.py"


def test_metadata_keys_are_snake_case(tmp_path: Path):
    # Backend's TemplateUploadMetadata uses @JsonProperty("snake_case") for
    # compound names. Sending camelCase would silently drop fields without
    # a 400 because Jackson allows unknown properties by default.
    manifest = load_manifest(_write_manifest(tmp_path))
    meta = build_metadata(manifest, {})
    assert "display_name" in meta
    assert "default_config" in meta
    assert "config_schema" in meta
    assert "source_visibility" in meta
    # No camelCase leakage
    for camel in ("displayName", "defaultConfig", "configSchema", "sourceVisibility"):
        assert camel not in meta


def test_metadata_serialises_to_json(tmp_path: Path):
    import json
    manifest = load_manifest(_write_manifest(tmp_path))
    meta = build_metadata(manifest, {"title": "s"})
    # Round-trip — if anything is non-JSON-safe it raises.
    assert json.loads(json.dumps(meta)) == meta
