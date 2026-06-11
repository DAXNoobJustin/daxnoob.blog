"""Central topic -> model routing.

Each model's ``model.json`` is the single source of truth for which model owns
which user-facing topics (its top-level ``title`` + per-row ``route:{name,
triggers}`` blocks). ``routing.json`` holds only the cross-model ``modelOrder``
and the shared description config. Together they drive two things:

1. The cross-model "reroute" section injected into each model's always-on router
   (so a model queried directly — e.g. via M365 Copilot — can tell the user when
   a question really belongs to a sibling model and where to go).
2. The thin cross-model router skill (``emit_router.py`` ->
   ``generated/adia-router.SKILL.md``): a high-level router that owns no detail
   and points each topic at its owning model. Because topic ownership lives on
   each model once, the router is generated from that same source — no extra
   source needs editing.

A sibling is only routed to when it is *active* (its canonical
`models/<slug>/model.json` exists). This keeps a model byte-exact
until its siblings actually have deployable instructions, and lights routing up
automatically once they do.

The rendered section keeps GUID tokens (`{{model-guid:<slug>}}`) unresolved; the
caller (emit_model) detokenizes the assembled router in one pass so per-env GUID
swaps apply uniformly.
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import model_json_path, models_dir

ROUTING_FILENAME = "routing.json"


def load_routing(canonical_root: Path) -> dict:
    path = canonical_root / ROUTING_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"{ROUTING_FILENAME} not found at {path} - it is the required single "
            "source of cross-model order + description config."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_model_meta(canonical_root: Path, slug: str) -> dict:
    """The routing-facing view of a model, derived from its ``model.json``.

    Returns ``{"title": str, "topics": [{"name", "triggers"}, ...]}`` where
    ``topics`` are the user-facing routing topics in row order — exactly the
    rows that carry a ``route`` block (structural rows like ``model-reference``
    and ``out-of-scope`` carry none). ``model.json`` is the single per-model
    registry: title and topic ownership live there, never in ``routing.json``.
    """
    mj = model_json_path(canonical_root, slug)
    model = json.loads(mj.read_text(encoding="utf-8"))
    embedded = model.get("slug")
    if embedded and embedded != slug:
        raise ValueError(
            f"model.json under '{slug}' declares a different slug '{embedded}' "
            "(folder and embedded slug must match)"
        )
    title = model.get("title")
    if not title or not isinstance(title, str):
        raise ValueError(f"{slug} model.json is missing a string top-level 'title'")
    topics = []
    for row in model.get("rows", []):
        if "route" not in row:
            raise ValueError(
                f"{slug} row '{row.get('anchor')}' must declare 'route' — use "
                '"route": null for a structural (non-routing) row, or a '
                '{"name", "triggers"} block for a user-facing topic'
            )
        route = row["route"]
        if route is None:
            continue
        name, triggers = route.get("name"), route.get("triggers")
        if not (isinstance(name, str) and name and isinstance(triggers, str) and triggers):
            raise ValueError(
                f"{slug} row '{row.get('anchor')}' route must have non-empty "
                "string 'name' and 'triggers'"
            )
        topics.append({"name": name, "triggers": triggers})
    return {"title": title, "topics": topics}


def _is_active(canonical_root: Path, slug: str) -> bool:
    return model_json_path(canonical_root, slug).exists()


def active_models(canonical_root: Path) -> list[str]:
    """Slugs (in ``routing.json`` ``modelOrder``) that have a canonical
    instruction set on disk.

    A model is *active* once its ``models/<slug>/model.json`` exists.
    This is the single definition of "active"; the emitter, the router generator,
    and the tests all consume it so the notion can never drift between them.
    ``modelOrder`` is required and must be a non-empty list (fail loud rather than
    silently emitting an empty router)."""
    order = load_routing(canonical_root).get("modelOrder")
    if not isinstance(order, list) or not order:
        raise ValueError("routing.json must declare a non-empty 'modelOrder' list")
    # Fail loud on the genuinely-broken direction: a model.json that exists on
    # disk but is absent from modelOrder would deploy yet be invisible to
    # cross-model routing / the thin router. (The reverse — a slug in modelOrder
    # without a model.json yet — is allowed: it stays inactive until its
    # instructions land, keeping siblings byte-exact in the meantime.)
    md = models_dir(canonical_root)
    on_disk = (
        {d.name for d in md.iterdir() if (d / "model.json").exists()}
        if md.exists()
        else set()
    )
    orphans = sorted(on_disk - set(order))
    if orphans:
        raise ValueError(
            f"models {orphans} have a model.json on disk but are missing from "
            "routing.json 'modelOrder' — add them to modelOrder (a deployed "
            "model not in modelOrder is invisible to cross-model routing)"
        )
    return [slug for slug in order if _is_active(canonical_root, slug)]


def active_siblings(canonical_root: Path, self_slug: str) -> list[str]:
    """Active slugs (in ``modelOrder``) other than ``self_slug``."""
    return [slug for slug in active_models(canonical_root) if slug != self_slug]


def _esc_cell(text: str) -> str:
    """Escape a value for safe inclusion in a markdown table cell."""
    return text.replace("|", "\\|")


def render_cross_model_section(canonical_root: Path, self_slug: str) -> str:
    """Tokenized markdown rerouting block for `self_slug`'s router, or "" when
    there are no active siblings (so the router stays byte-exact). Grouped by
    sibling model: an H3 heading carries the model's dataset GUID once, then a
    Topic/Signals table lists that model's topics (one row each), so the long
    GUID is not repeated on every topic row."""
    siblings = active_siblings(canonical_root, self_slug)
    if not siblings:
        return ""

    lines = [
        "## Other Ask ADIA models — reroute for their topics",
        "",
        "If the question is really about a topic below, it lives in a "
        "**different** semantic model. Tell the user which model to query (or "
        "switch to it) — do not answer it from this model.",
    ]
    for slug in siblings:
        meta = load_model_meta(canonical_root, slug)
        guid_token = f"{{{{model-guid:{slug}}}}}"
        lines += [
            "",
            f"### {_esc_cell(meta['title'])} — dataset `{guid_token}`",
            "",
            "| Topic | Signals |",
            "| --- | --- |",
        ]
        for t in meta["topics"]:
            lines.append(f"| {_esc_cell(t['name'])} | {_esc_cell(t['triggers'])} |")
    return "\n".join(lines) + "\n"


def render_out_of_scope(canonical_root: Path, self_slug: str) -> str:
    """Generate the slim out-of-scope row body (model-agnostic).

    The always-on router already carries this model's **Topic index** (its
    supported topics) and the **Other Ask ADIA models — reroute** section (each
    sibling's title, GUID, and topics). Restating either here just duplicated two
    always-on sections that can drift, so this fetched row is purely the
    deny/reroute *decision rule* and points back at that always-on guidance for
    the actual lists. ``canonical_root`` / ``self_slug`` are unused but kept so the
    generated-row dispatch can call every renderer uniformly.

    The ``{{ref:...}}`` tokens are left unresolved for the emitter's single
    detokenize pass.
    """
    return (
        "## When NOT to Use This Model\n"
        "\n"
        "A question matching **none** of this model's supported topics (see the "
        "**Topic index** in the always-on guidance) is out of scope — including "
        'raw fact-table exploration ("scan table X for a keyword", "list every '
        'distinct value of column Y") or an untrained metric. Classify and deny '
        "per the Workflow ({{ref:workflow}}): the curated UDFs only surface "
        "trained measures + annotated columns, and custom DAX is a trained-topic "
        "last resort (Escape Hatch, {{ref:output-formatting}}). Do not improvise.\n"
        "\n"
        "If it really belongs to a **sibling model**, route the user there using "
        "the **Other Ask ADIA models — reroute** section in the always-on "
        "guidance — never answer a sibling model's topic from this model.\n"
    )
