"""Generate the thin Ask ADIA *router* skill from ``routing.json``.

The pivot makes the consumer skill a high-level router only: it owns no query
workflow, UDF reference, or formatting — each semantic model's own always-on
``_COPILOT_INSTRUCTIONS`` guidance carries all of that and self-routes when queried
directly. This generator turns each model's ``model.json`` (title + route blocks)
into that router so the topic ownership lives on the model in exactly one place.

Output keeps ``{{model-guid:<slug>}}`` tokens unresolved; the consumer's own deploy
resolves them per environment (the same token contract the model emitter uses).
Only *active* models (those with a canonical ``model.json`` on disk) are emitted,
mirroring the cross-model reroute logic in ``_core.routing``.

The rendered artifact is committed at ``generated/adia-router.SKILL.md`` as a
reviewable preview + drift golden — the same thin router a consumer skill would
ship, kept in sync with the models via this generator. Nothing here writes
outside this repo.

CLI::

    python emit_router.py                 # print rendered router to stdout
    python emit_router.py --check         # fail if the committed artifact is stale
    python emit_router.py --update-golden # rewrite the committed artifact
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _core.routing import active_models, load_model_meta

HERE = Path(__file__).resolve().parent
ARTIFACT_REL = "generated/adia-router.SKILL.md"

_PROVENANCE = (
    "<!--\n"
    "  GENERATED FILE - do not edit by hand.\n"
    "  Source of truth: each model's model.json (title + route blocks) +\n"
    "  routing.json modelOrder (askadia/instructions/).\n"
    "  Regenerate: python emit_router.py --update-golden\n"
    "  Illustrative preview of the thin router a consumer skill would ship,\n"
    "  kept in sync with the models via this generator.\n"
    "  GUID tokens ({{model-guid:<slug>}}) are resolved per-environment at\n"
    "  the consumer's deploy time.\n"
    "-->"
)


def _active_models(canonical_root: Path) -> list[str]:
    """Slugs in ``modelOrder`` that have a canonical ``model.json``."""
    return active_models(canonical_root)


def _frontmatter(metas: dict[str, dict]) -> str:
    coverage = "; ".join(
        f"{m['title']} ({', '.join(t['name'] for t in m['topics'])})"
        for m in metas.values()
    )
    triggers = ", ".join(
        f'"{t["name"]}"' for m in metas.values() for t in m["topics"]
    )
    desc = (
        "Router for the Azure Data (ADIA) curated Power BI semantic models. "
        "Given a business question, identify the right model and topic and query "
        "it - each model's _COPILOT_INSTRUCTIONS table carries the full workflow, "
        f"UDF reference, and formatting rules. Coverage: {coverage}. "
        f"Triggers: {triggers}."
    )
    return "\n".join(["---", "type: skill", "name: adia-router", f"description: >", f"  {desc}", "---"])


def render(canonical_root: Path = HERE) -> str:
    """Render the thin router skill markdown (GUIDs left as tokens)."""
    slugs = _active_models(canonical_root)
    metas = {slug: load_model_meta(canonical_root, slug) for slug in slugs}

    parts: list[str] = [_frontmatter(metas), "", _PROVENANCE, ""]
    parts += [
        "# Ask ADIA - Model Router",
        "",
        "You route Azure Data business questions to the right curated Power BI "
        "semantic model. You do **not** answer from memory and you do **not** "
        "carry the detailed query workflow here - each model's own always-on "
        "`_COPILOT_INSTRUCTIONS` guidance holds the UDF reference, per-topic rules, "
        "report templates, and formatting. Your job: pick the right model + "
        "topic, query that model, and follow the guidance it returns.",
        "",
        "## How to route",
        "",
        "1. Match the user's question to exactly one model + topic from the "
        "tables below.",
        "2. Query that model with the `FabricIQ` MCP `ExecuteQuery` tool using "
        "the model's artifact GUID. The model's full guidance lives in its "
        "`_COPILOT_INSTRUCTIONS` table (you reach it over DAX, not as an attached "
        "system prompt). First discover the rows - `EVALUATE "
        "SELECTCOLUMNS('_COPILOT_INSTRUCTIONS', \"Key\", [Key], \"Topic\", [Topic], "
        "\"When to use\", [WhenToUse])` - then fetch the bodies you need by their "
        "**key**, e.g. `EVALUATE FILTER('_COPILOT_INSTRUCTIONS', [Key] IN "
        "{ \"workflow\" })`. Always start with the always-on `workflow` row and "
        "follow what these rows return as the source of truth.",
        "3. If, once you read the model guidance, the intent actually belongs to "
        "a different model, switch to that model instead - never answer a topic "
        "from the wrong model.",
        "4. If nothing matches, name the trained topics across the models and "
        "stop. Do not improvise or run ad-hoc DAX.",
        "",
        "## Models & topics",
        "",
    ]

    for slug in slugs:
        model = metas[slug]
        parts.append(f"### {model['title']}")
        parts.append("")
        parts.append(f"Artifact GUID: `{{{{model-guid:{slug}}}}}`")
        parts.append("")
        parts.append("| Topic | Signals |")
        parts.append("|---|---|")
        for t in model["topics"]:
            parts.append(f"| {t['name']} | {t['triggers']} |")
        parts.append("")

    parts += [
        "## Critical rules",
        "",
        "- Never fabricate numbers - every value comes from a DAX query against "
        "the model.",
        "- Resolve user-named values (accounts, partners, products) at query time "
        "via the model's `SearchValues` / `SearchHierarchy` UDFs; never hard-code "
        "them from memory.",
        "- For Power BI outside these models, use the standard Power BI "
        "consumption path instead of this router.",
    ]
    return "\n".join(parts) + "\n"


def update_golden(canonical_root: Path = HERE) -> Path:
    """Write the rendered router to the committed artifact path."""
    dest = canonical_root / ARTIFACT_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(canonical_root), encoding="utf-8", newline="\n")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canonical-root", type=Path, default=HERE)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--update-golden", action="store_true")
    args = ap.parse_args()

    rendered = render(args.canonical_root)

    if args.update_golden:
        dest = update_golden(args.canonical_root)
        print(f"Updated router artifact: {dest.relative_to(args.canonical_root)}")
        return 0

    artifact = args.canonical_root / ARTIFACT_REL
    if args.check:
        if not artifact.exists():
            print(f"Router artifact missing: {ARTIFACT_REL}", file=sys.stderr)
            return 1
        if artifact.read_bytes().decode("utf-8") != rendered:
            print(f"Router artifact is stale: {ARTIFACT_REL}", file=sys.stderr)
            return 1
        print("Router artifact up to date.")
        return 0

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
