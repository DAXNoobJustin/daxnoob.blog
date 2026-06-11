"""Generated model ``description`` written to the Fabric item's ``.platform``.

Copilot / M365 and the Fabric catalog read the item description (``.platform``
``metadata.description``) for grounding + model selection, and the platform caps
it at 500 characters. The generated description is derived from the per-model
``model.json`` topic list (the same list that drives cross-model routing), so it
can never drift from the manifest and there is no second list to maintain.

If a model already ships a hand-authored description, it is **preserved** as the
lead-in and the generated "Trained topics: ..." sentence is appended after it
(combine). A placeholder that merely repeats the item ``displayName`` is treated
as no lead-in. Models with no curated description get the full template sentence.

It is injected into the *staged* ``.platform`` at deploy (never source-controlled
on the model), exactly like the ``_COPILOT_INSTRUCTIONS`` table + always-on router.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .paths import model_json_path
from .routing import load_model_meta, load_routing

MAX_DESCRIPTION_LEN = 500


def _curated_lead_in(
    existing: str | None, template: str, suffix: str, display_name: str | None = None
) -> str | None:
    """Recover the *hand-authored* lead-in from a model's current description.

    Idempotency: a previously appended generated suffix is stripped, a description
    that is wholly our own template (no curated text) is treated as having no
    lead-in, and a placeholder equal to the item ``displayName`` is ignored — so
    re-running build/apply reproduces the same string.
    """
    if not existing:
        return None
    suffix_prefix = re.escape(suffix.split("{", 1)[0].strip())
    lead = re.sub(rf"\s*{suffix_prefix}.*$", "", existing.strip()).strip()
    if not lead:
        return None
    if display_name and lead == display_name.strip():
        return None
    template_lead = template.split("{", 1)[0].strip()
    if template_lead and lead.startswith(template_lead):
        return None
    return lead


def build_description(
    canonical_root: Path,
    slug: str,
    existing: str | None = None,
    max_len: int = MAX_DESCRIPTION_LEN,
    display_name: str | None = None,
) -> str:
    """Render the model description from the model's ``model.json`` topics.

    Topics come from the model's ``route`` rows (in row order) via
    ``load_model_meta``; the description template/suffix/scope come from
    ``routing.json`` (``descriptionScope`` may be overridden per model in
    ``model.json``). The config keys are required — a missing key fails loud
    rather than falling back to a code default, so the single source of config
    is ``routing.json``.

    When ``existing`` (the model's current curated description) is supplied and is
    neither our generated template nor a bare ``display_name`` placeholder, it is
    kept as the lead-in and the topics sentence is appended. Raises if the result
    exceeds ``max_len`` so an over-long description fails the deploy/CI gate instead
    of being silently truncated by the platform.
    """
    routing = load_routing(canonical_root)
    meta = load_model_meta(canonical_root, slug)
    try:
        template = routing["descriptionTemplate"]
        suffix = routing["descriptionTopicsSuffix"]
        global_scope = routing["descriptionScope"]
    except KeyError as exc:
        raise ValueError(
            f"routing.json is missing required description config key {exc}"
        ) from exc
    model = json.loads(model_json_path(canonical_root, slug).read_text(encoding="utf-8"))
    scope = model.get("descriptionScope", global_scope)
    topics = ", ".join(t["name"] for t in meta["topics"])

    lead = _curated_lead_in(existing, template, suffix, display_name)
    if lead:
        description = f"{lead} {suffix.format(topics=topics)}"
    else:
        description = template.format(scope=scope, topics=topics)

    if len(description) > max_len:
        raise ValueError(
            f"{slug} model description is {len(description)} chars (> {max_len} cap): "
            f"{description!r}"
        )
    return description


def read_platform_description(platform_path: Path) -> str | None:
    """Return ``metadata.description`` from a ``.platform`` file, or None."""
    data = json.loads(Path(platform_path).read_text(encoding="utf-8"))
    desc = (data.get("metadata") or {}).get("description")
    return desc.strip() if isinstance(desc, str) and desc.strip() else None


def read_platform_display_name(platform_path: Path) -> str | None:
    """Return ``metadata.displayName`` from a ``.platform`` file, or None."""
    data = json.loads(Path(platform_path).read_text(encoding="utf-8"))
    name = (data.get("metadata") or {}).get("displayName")
    return name.strip() if isinstance(name, str) and name.strip() else None


def apply_platform_description(platform_path: Path, description: str) -> None:
    """Set ``metadata.description`` on a ``.platform`` file (idempotent).

    Preserves key order and the 2-space indentation used by the staging rebrand
    (``lib/staging.py``) so re-applying produces a byte-identical file.
    """
    path = Path(platform_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("metadata", {})["description"] = description
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
