# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""
`lyrithm.yaml` manifest parser + validator.

Every strategy package ships a `lyrithm.yaml` describing identity, language,
entrypoint, default config, and a JSON Schema for tunable parameters. The
platform uses this manifest to render config UIs and validate user overrides.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

SUPPORTED_LANGUAGES = ("python", "java", "pine")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class ManifestError(ValueError):
    """Raised when a lyrithm.yaml manifest fails validation."""


@dataclass
class Manifest:
    name: str
    display_name: str
    language: str
    entrypoint: str
    version: str
    description: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)
    default_config: Dict[str, Any] = field(default_factory=dict)
    config_schema_path: Optional[str] = None
    source_visibility: str = "closed"  # 'closed' | 'open'

    @property
    def is_open_source(self) -> bool:
        return self.source_visibility == "open"

    def load_config_schema(self, base_dir: Path) -> Dict[str, Any]:
        if not self.config_schema_path:
            return {}
        schema_file = base_dir / self.config_schema_path
        if not schema_file.exists():
            raise ManifestError(f"config_schema not found: {schema_file}")
        return json.loads(schema_file.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> Manifest:
    """Parse and validate a lyrithm.yaml file from disk."""
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"manifest not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _validate(raw)


def _validate(raw: Dict[str, Any]) -> Manifest:
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a mapping")

    required = ("name", "display_name", "language", "entrypoint", "version")
    for key in required:
        if key not in raw or raw[key] in (None, ""):
            raise ManifestError(f"missing required field: {key}")

    name = str(raw["name"])
    if not NAME_RE.match(name):
        raise ManifestError(
            f"invalid name '{name}'; must match {NAME_RE.pattern} "
            "(lowercase, digits, hyphens; 2-63 chars; starts with letter)"
        )

    language = str(raw["language"]).lower()
    if language not in SUPPORTED_LANGUAGES:
        raise ManifestError(
            f"invalid language '{language}'; must be one of {SUPPORTED_LANGUAGES}"
        )

    version = str(raw["version"])
    if not SEMVER_RE.match(version):
        raise ManifestError(f"invalid version '{version}'; must be semver (e.g. 1.0.0)")

    entrypoint = str(raw["entrypoint"])
    if "/" in entrypoint or "\\" in entrypoint or ".." in entrypoint:
        raise ManifestError(
            f"entrypoint '{entrypoint}' must be a single filename, not a path"
        )

    visibility = str(raw.get("source_visibility", "closed")).lower()
    if visibility not in ("closed", "open"):
        raise ManifestError(
            f"invalid source_visibility '{visibility}'; must be 'closed' or 'open'"
        )

    default_config = raw.get("default_config") or {}
    if not isinstance(default_config, dict):
        raise ManifestError("default_config must be a mapping")

    tags = raw.get("tags") or []
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ManifestError("tags must be a list of strings")

    return Manifest(
        name=name,
        display_name=str(raw["display_name"]),
        language=language,
        entrypoint=entrypoint,
        version=version,
        description=str(raw.get("description", "")),
        author=str(raw.get("author", "")),
        tags=list(tags),
        default_config=dict(default_config),
        config_schema_path=raw.get("config_schema"),
        source_visibility=visibility,
    )
