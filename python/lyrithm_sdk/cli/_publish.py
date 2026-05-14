# Copyright 2026 Jay Cheng
# Licensed under the Apache License, Version 2.0 (see LICENSE).
"""`lyrithm publish` — upload a packaged strategy to the Lyrithm platform.

POSTs multipart to `<api>/api/v1/templates`:
  * source  — the entrypoint file bytes (closed-source: server stores under
              data/strategies/_protected/<template_id>/)
  * metadata — JSON: {name, display_name, language, entrypoint, version,
                      description, default_config, config_schema,
                      source_visibility, tags}

The server replies with the new template_id. Behind feature flag
STRATEGY_UPLOAD_ENABLED on the platform side.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import click
import requests

from ..manifest import Manifest, load_manifest


# Fields the backend's TemplateUploadMetadata DTO requires; tests pin this
# set so a future drop will be caught at unit-test time, not by 400 in the
# wild. Keep in sync with TemplateUploadMetadata.java.
REQUIRED_METADATA_FIELDS = frozenset({
    "name",
    "display_name",
    "language",
    "entrypoint",
    "version",
    "source_visibility",
})


def build_metadata(manifest: Manifest, config_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Build the JSON metadata blob sent as the ``metadata`` multipart part.
    Extracted so the unit tests can assert the wire contract without
    spinning up the CLI runner."""
    return {
        "name": manifest.name,
        "display_name": manifest.display_name,
        "language": manifest.language,
        "entrypoint": manifest.entrypoint,
        "version": manifest.version,
        "description": manifest.description,
        "tags": manifest.tags,
        "default_config": manifest.default_config,
        "config_schema": config_schema,
        "source_visibility": manifest.source_visibility,
    }


@click.command()
@click.option(
    "--project",
    "project_dir",
    default=".",
    help="Strategy project directory. Defaults to cwd.",
)
@click.option(
    "--api",
    "api_url",
    default=None,
    help="Lyrithm API base URL. Defaults to $LYRITHM_API or http://127.0.0.1:8080.",
)
@click.option(
    "--token",
    default=None,
    help="API token. Defaults to $LYRITHM_API_TOKEN (Phase 2: Clerk-issued JWT).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate manifest + show the request payload; do not POST.",
)
def publish(project_dir: str, api_url: str | None, token: str | None, dry_run: bool) -> None:
    """Upload the strategy at PROJECT to the Lyrithm platform."""
    project = Path(project_dir).resolve()
    manifest = load_manifest(project / "lyrithm.yaml")
    entrypoint = project / manifest.entrypoint
    if not entrypoint.exists():
        raise click.ClickException(f"entrypoint not found: {entrypoint}")
    schema = manifest.load_config_schema(project)

    api_url = api_url or os.environ.get("LYRITHM_API") or "http://127.0.0.1:8080"
    api_url = api_url.rstrip("/")
    token = token or os.environ.get("LYRITHM_API_TOKEN")

    metadata = build_metadata(manifest, schema)

    if dry_run:
        click.echo(f"[dry-run] POST {api_url}/api/v1/templates")
        click.echo(f"[dry-run] source: {entrypoint} ({entrypoint.stat().st_size} bytes)")
        click.echo("[dry-run] metadata:")
        click.echo(json.dumps(metadata, indent=2))
        return

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with entrypoint.open("rb") as fh:
        files = {
            "source": (entrypoint.name, fh, "text/plain"),
            "metadata": (None, json.dumps(metadata), "application/json"),
        }
        resp = requests.post(
            f"{api_url}/api/v1/templates",
            headers=headers,
            files=files,
            timeout=30,
        )

    if resp.status_code >= 400:
        raise click.ClickException(f"upload failed ({resp.status_code}): {resp.text}")

    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    # Server returns camelCase per Jackson; older payload variants used
    # snake_case. Accept either so the CLI does not flap on field-name drift.
    status = body.get("publishStatus") or body.get("publish_status") or "?"
    click.echo(f"Published. template_id={body.get('id', '?')}  status={status}")
