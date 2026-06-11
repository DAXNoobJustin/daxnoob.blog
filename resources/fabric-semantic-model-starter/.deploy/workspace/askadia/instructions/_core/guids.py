"""Resolve the per-model Copilot dataset GUID map from a workspace config.

The single source of GUID *values* is a config holding a ``copilot_model_guids``
map of ``slug -> {env: guid}`` with a required ``prod`` baseline, for example::

    copilot_model_guids:
      azure-data-insights:
        dev:   "<dev dataset guid>"
        test:  "<test dataset guid>"
        prod:  "aaaaaaaa-aaaa-aaaa-aaaa-000000000016"

This module is the ONLY reader of that map.  The model emitter takes the already
resolved ``{slug: guid}`` dict by injection, so the renderer stays
config-source-agnostic (and therefore portable to another team's layout): point
:func:`load_guids` at any config and pass the result to ``emit_model.render``.

Env resolution is **explicit, with no fallback**: the requested environment must
have its own GUID for every model, otherwise resolution fails loudly. This keeps
cross-model routing honest — a dev/test deploy can never silently point
at the prod datasets. ``prod`` is still required as the canonical baseline.
"""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_CONFIG_KEY = "copilot_model_guids"

_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def resolve_guids(raw_map: dict, env: str = "prod") -> dict[str, str]:
    """Resolve a ``slug -> {env: guid}`` mapping to ``slug -> guid`` for ``env``.

    Resolution is explicit: the requested ``env`` must have its own GUID for every
    model (no prod fallback). Fails loudly on a malformed map: a non-mapping input,
    a slug whose value is not a mapping, a missing/empty ``prod`` baseline, a
    missing key for the requested env, an empty value, or a value that is not a
    well-formed GUID.
    """
    if not isinstance(raw_map, dict) or not raw_map:
        raise ValueError("copilot_model_guids must be a non-empty mapping")
    key = (env or "prod").lower()
    out: dict[str, str] = {}
    for slug, per_env in raw_map.items():
        if not isinstance(per_env, dict):
            raise ValueError(f"copilot_model_guids.{slug} must be a mapping of env -> guid")
        if not per_env.get("prod"):
            raise ValueError(f"copilot_model_guids.{slug} is missing a non-empty 'prod' baseline")
        if key not in per_env:
            available = ", ".join(sorted(per_env))
            raise ValueError(
                f"copilot_model_guids.{slug} has no '{key}' GUID (available: {available}). "
                f"Add an explicit per-env GUID; there is no prod fallback."
            )
        value = per_env[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"copilot_model_guids.{slug}.{key} is empty or not a string")
        if not _GUID_RE.match(value.strip()):
            raise ValueError(f"copilot_model_guids.{slug}.{key} is not a valid GUID: {value!r}")
        out[slug] = value.strip()
    return out


def load_guids(
    config_path, env: str = "prod", key: str = DEFAULT_CONFIG_KEY
) -> dict[str, str]:
    """Load and resolve the GUID map from a YAML config file.

    ``key`` is configurable so an adopting team can store the map under a
    different top-level key.  ``yaml`` is imported lazily so :func:`resolve_guids`
    stays dependency-free for callers that already hold the parsed mapping.
    """
    import yaml  # noqa: PLC0415

    path = Path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get(key)
    if not raw:
        raise KeyError(f"No '{key}' map in {path}")
    return resolve_guids(raw, env)
