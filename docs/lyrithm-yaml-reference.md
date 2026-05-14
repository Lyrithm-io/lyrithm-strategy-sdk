# `lyrithm.yaml` reference

Every strategy package ships a `lyrithm.yaml` describing identity, language, entrypoint, default config, and (separately, by reference) a JSON Schema for tunable parameters.

## Full example

```yaml
name: ema-cross
display_name: "EMA Cross — Minimal Example"
language: python
entrypoint: strategy.py
version: 0.1.0
description: "Trivial EMA crossover demo."
author: "Your Name"
tags: [example, trend-following]
source_visibility: open
config_schema: config_schema.json
default_config:
  ema_fast: 12
  ema_slow: 26
```

## Fields

| Field | Required | Type | Notes |
|---|:-:|---|---|
| `name` | ✓ | string | Lowercase letters/digits/hyphens, 2–63 chars, starts with a letter. Used as the platform identifier; must be unique per owner. |
| `display_name` | ✓ | string | Human-friendly name shown in the dashboard. |
| `language` | ✓ | enum | `python` (Phase 1) · `java` (Phase 2) · `pine` (Phase 3). |
| `entrypoint` | ✓ | string | Single filename (no path components). For Python: the file containing `create_strategy` or your `Strategy` subclass. |
| `version` | ✓ | semver | `MAJOR.MINOR.PATCH`, optional `-prerelease` / `+build`. |
| `description` | – | string | One-paragraph summary. Shown on the marketplace card. |
| `author` | – | string | Free-form attribution. |
| `tags` | – | string[] | Searchable tags. |
| `source_visibility` | – | enum | `closed` (default) — users use/tune but never see source; `open` — forkable. Mirrors TradingView "Protected" vs "Open" Pine semantics. |
| `config_schema` | – | path | Filename of a JSON Schema describing tunable fields. The dashboard renders this into a form. |
| `default_config` | – | object | Default values consumed by `Strategy.__init__`. Users provide a *diff* (override) on top of this — they never have to start from scratch. |

## Naming the strategy

`name` is what appears in URLs, API responses, and the marketplace. It cannot change after publish (changing it would break instance references). Pick something stable.

## `config_schema` shape

Group-oriented JSON intended to be rendered as a form by the dashboard:

```json
{
  "title": "EMA Cross",
  "groups": [
    {
      "name": "EMA",
      "fields": {
        "ema_fast": { "type": "integer", "min": 2, "max": 500, "default": 12, "label": "EMA Fast", "tunable": true }
      }
    }
  ]
}
```

Per-field properties:

| Property | Notes |
|---|---|
| `type` | `integer` · `number` · `boolean` · `string` · `enum` · `array` |
| `min` / `max` | Numeric bounds (enforced server-side via JSON Schema validator). |
| `default` | Default value — must match the top-level `default_config` in `lyrithm.yaml`. |
| `label` | Human-friendly form label. |
| `tunable` | If `false`, the field is locked from user overrides (typically arrays of rule toggles that change logic shape). |
| `values` | For `enum` type — array of allowed values. |
| `items` / `length` | For `array` type — element type and required length. |

## `source_visibility` semantics

| Value | Users see source? | Forkable? | Use case |
|---|:-:|:-:|---|
| `closed` (default) | No | No (always 403) | Author keeps IP. TradingView "Protected / Invite-only" model. |
| `open` | Yes (in dashboard) | Yes — server clones source into new user-owned template | Educational examples, community contributions. |

Choosing `closed` does **not** delete source from the server — it only blocks API exposure. Server admins (you) retain physical access for safety review. Phase 1.4 documents the audit policy and consent flow.

## Versioning rules

- Bumping `version` triggers a `ConfigPoller` reload across all running instances pointing at the template.
- The platform keeps the previous source file alongside the new one (for one release) so in-flight sessions finish on the old code; new sessions get the new code.
- Breaking config shape changes: bump MAJOR; the platform will refuse to start instances whose `config_override` doesn't satisfy the new schema.
