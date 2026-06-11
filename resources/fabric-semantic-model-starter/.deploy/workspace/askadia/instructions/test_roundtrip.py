"""Self-contained tests for the canonical instruction toolkit.

Run with:  python -m pytest test_roundtrip.py    (from the instructions dir)
or:        python test_roundtrip.py               (no pytest needed)

These do not depend on any consumer checkout: they exercise the single neutral
instruction store (``common/`` + ``models/<slug>/``) that lives in this repo and
assert the invariants the ``emit_model`` / ``emit_router`` renderers rely on.
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

from _core.tokens import find_tokens
from _core.model_table import parse_table, render_table
from _core.paths import (
    SHARED_ANCHORS,
    block_path,
    manifest_path,
    model_json_path,
    model_rows_dir,
    models_dir,
    common_dir,
)
from _core.tmdl import InstructionRow, parse_union, render_union
from _core.guids import load_guids, resolve_guids
import emit_model

HERE = Path(__file__).resolve().parent
MODEL_GUIDS_YML = HERE.parent / "config" / "model_guids.yml"


@contextlib.contextmanager
def _assert_raises(exc_type, match: str | None = None):
    """Stdlib stand-in for ``pytest.raises`` so the suite runs with no pytest
    dependency (as the module docstring promises) under both the manual
    ``__main__`` runner and ``python -m pytest``."""
    try:
        yield
    except exc_type as exc:
        if match is not None and not re.search(match, str(exc)):
            raise AssertionError(
                f"{exc_type.__name__} raised but message {str(exc)!r} "
                f"does not match {match!r}"
            ) from exc
        return
    raise AssertionError(f"expected {exc_type.__name__} to be raised")


def _prod_guids() -> dict[str, str]:
    """Per-model production dataset GUIDs (single source: config/model_guids.yml)."""
    return load_guids(MODEL_GUIDS_YML, "prod")


PROD_GUIDS = _prod_guids()


def _slug_by_guid() -> dict[str, str]:
    return {guid: slug for slug, guid in PROD_GUIDS.items()}

# The authored models that ship instructions — used to assert the active model
# set / routing map stays in sync (not an exact row-count pin).
EXPECTED_MODELS = (
    "azure-data-insights",
    "azure-data-partner-community",
)


def _active_models() -> list[str]:
    """Routing-map slugs that have a canonical model.json on disk."""
    from _core.routing import active_models

    return active_models(HERE)


def _all_body_paths() -> list[Path]:
    """Every authored row body: the shared blocks plus each active model's rows."""
    bodies = list((common_dir(HERE) / "blocks").glob("*.md"))
    for slug in _active_models():
        bodies += list(model_rows_dir(HERE, slug).glob("*.md"))
    return bodies


def test_model_emitter_consumes_only_content() -> None:
    """The single-source store is the only authored copy: the legacy ``content/``
    tree and the dual-copy skill stores are gone, yet the model emitter still
    produces its full file set from ``common/`` + ``models/<slug>/rows/``."""
    assert (common_dir(HERE) / "blocks").is_dir(), "common/blocks store missing"
    assert models_dir(HERE).is_dir(), "models/ store missing"
    for stale in ("skill", "shared-rows", "content"):
        assert not (HERE / stale).exists(), f"legacy {stale}/ still present"
    for slug in _active_models():
        out = emit_model.render(HERE, slug, PROD_GUIDS)
        assert set(out) == {
            "definition/tables/_COPILOT_INSTRUCTIONS.tmdl",
            "Copilot/Instructions/instructions.md",
        }


def test_guids_only_in_manifest() -> None:
    """No literal prod GUID may appear in canonical bodies (single source:
    config/model_guids.yml, resolved only at emit time)."""
    slug_by_guid = _slug_by_guid()
    for path in _all_body_paths():
        text = path.read_text(encoding="utf-8")
        for guid in slug_by_guid:
            assert guid not in text, f"Literal GUID {guid} leaked into {path}"


def test_tmdl_codec_roundtrip() -> None:
    """render -> parse must round-trip rows with quotes, newlines, unicode."""
    rows = [
        InstructionRow(1, "alpha", 'Topic "A"', "Triggers: x, y", '# H\n\nLine with ""quotes""\n'),
        InstructionRow(2, "beta", "Topic — B", "When: z", "Bullet\n- a\n- b"),
    ]
    parsed = parse_union(render_union(rows))
    assert parsed == rows
    parsed_tbl = parse_table(render_table(rows))
    assert parsed_tbl == rows


def test_model_emit_resolves_all_tokens() -> None:
    """Emitting any active model must leave no unresolved tokens. The model no
    longer quotes its OWN artifact GUID anywhere in its instructions (the agent
    already operates on its connected artifact); a model's GUID only appears in
    its SIBLINGS' cross-model reroute sections, never in its own table."""
    for slug in _active_models():
        rendered = emit_model.render(HERE, slug, PROD_GUIDS)
        for rel, content in rendered.items():
            assert not find_tokens(content), f"Unresolved tokens in {slug}:{rel}"
        tmdl = rendered["definition/tables/_COPILOT_INSTRUCTIONS.tmdl"]
        assert PROD_GUIDS[slug] not in tmdl, (
            f"{slug} must not quote its own GUID in its _COPILOT_INSTRUCTIONS table"
        )


def test_malformed_token_is_caught_not_shipped() -> None:
    """A typo'd token (space in the ref arg, or an unknown kind) doesn't match the
    strict token grammar, so ``detokenize`` leaves it intact rather than failing.
    The residual-brace guard must flag the leftover ``{{...}}`` so a typo can never
    silently ship literal braces into deployed model instructions."""
    from _core.tokens import TokenMap, detokenize, find_residual_tokens, find_tokens

    bad = "see the {{ref:bad anchor}} row and {{bogus:workflow}} too."
    tmap = TokenMap(guids={}, refs={"workflow": "`workflow`"})
    out = detokenize(bad, tmap)
    assert "{{" in out  # neither malformed token matched the grammar
    assert not find_tokens(out)  # the well-formed-token check misses these
    assert find_residual_tokens(out), "guard must flag malformed leftover tokens"
    # A fully resolved body has no residue.
    good = detokenize("see {{ref:workflow}}.", tmap)
    assert not find_residual_tokens(good)
    # Report-template placeholders ({{UPPER_SNAKE}}, no inner colon) are legitimate
    # 360-row content and must NOT be flagged.
    assert not find_residual_tokens("Replace {{ACCOUNT_NAME}} (AccountKey {{AccountKey}}).")


def test_render_raises_on_malformed_token_in_body(tmp_path: Path) -> None:
    """End-to-end guard: a malformed token in a real content block must make
    emit_model.render() RAISE, not ship literal braces. Exercises the render
    validation loop (not just the unit helper)."""
    import shutil

    canon = tmp_path / "instructions"
    shutil.copytree(HERE, canon)
    block = canon / "common" / "blocks" / "workflow.md"
    block.write_text(
        block.read_text(encoding="utf-8") + "\nSee the {{ref:bad anchor}} row.\n",
        encoding="utf-8",
    )
    with _assert_raises(ValueError, "[Mm]alformed"):
        emit_model.render(canon, "azure-data-insights", PROD_GUIDS)


def test_model_does_not_quote_own_guid_anywhere() -> None:
    """A model never quotes its OWN artifact GUID in any of its own rendered
    output (table or always-on router) — the agent already operates on its
    connected artifact, so a self-quote is redundant. A model's GUID only
    surfaces in its SIBLINGS' cross-model reroute sections. Inject a sentinel
    self value and assert it appears nowhere in the model's own render."""
    fake = "00000000-0000-0000-0000-000000000000"
    for slug in _active_models():
        env_guids = {**PROD_GUIDS, slug: fake}
        rendered = emit_model.render(HERE, slug, env_guids)
        for rel, content in rendered.items():
            assert fake not in content, f"{slug} quotes its own GUID in {rel}"
            assert PROD_GUIDS[slug] not in content, (
                f"{slug} quotes its own prod GUID in {rel}"
            )


def test_sibling_guids_are_env_resolved_in_router() -> None:
    """A sibling's per-env GUID (not prod) appears in this model's reroute
    section when the injected map carries the env value for that sibling."""
    fake_sibling = "11111111-1111-1111-1111-111111111111"
    order = json.loads((HERE / "routing.json").read_text(encoding="utf-8"))["modelOrder"]
    active = _active_models()
    for slug in active:
        siblings = [s for s in order if s != slug and s in active]
        if not siblings:
            continue
        sib = siblings[0]
        env_guids = {**PROD_GUIDS, sib: fake_sibling}
        router = emit_model.render(HERE, slug, env_guids)[
            "Copilot/Instructions/instructions.md"
        ]
        section = router.split("## Other Ask ADIA models", 1)[1]
        assert fake_sibling in section, f"{slug} did not env-resolve sibling {sib}"
        assert PROD_GUIDS[sib] not in section


def test_render_fails_loud_on_missing_guid() -> None:
    """Rendering must raise if the injected map lacks this model or an active
    sibling (rather than emitting an unresolved token)."""
    slug = next(iter(_active_models()))
    with _assert_raises(KeyError):
        emit_model.render(HERE, slug, {})


def test_resolve_guids_env_and_validation() -> None:
    """resolve_guids honors per-env GUIDs with NO prod fallback, and fails loud on
    a missing prod baseline, a missing env key,     a malformed GUID, or an empty env
    value."""
    raw = {
        "model-a": {"prod": "aaaaaaaa-aaaa-aaaa-aaaa-000000000016",
                    "test": "00000000-0000-0000-0000-000000000000"},
        "model-b": {"prod": "aaaaaaaa-aaaa-aaaa-aaaa-000000000097",
                    "test": "11111111-1111-1111-1111-111111111111"},
    }
    # Case-insensitive env key; the per-env GUID is used (never prod) for that env.
    out = resolve_guids(raw, "TEST")
    assert out["model-a"] == "00000000-0000-0000-0000-000000000000"
    assert out["model-b"] == "11111111-1111-1111-1111-111111111111"
    # prod env resolves to the prod baseline.
    assert resolve_guids(raw, "prod")["model-a"] == raw["model-a"]["prod"]
    # No fallback: an env missing for any model fails loud.
    with _assert_raises(ValueError):
        resolve_guids(raw, "dev")
    with _assert_raises(ValueError):
        resolve_guids({"m": {"test": "00000000-0000-0000-0000-000000000000"}})  # no prod
    with _assert_raises(ValueError):
        resolve_guids({"m": {"prod": "not-a-guid"}})
    with _assert_raises(ValueError):
        resolve_guids({"m": {"prod": "aaaaaaaa-aaaa-aaaa-aaaa-000000000016", "test": ""}}, "test")
    with _assert_raises(ValueError):
        resolve_guids({})


def test_shared_row_grouping_is_well_formed() -> None:
    """The content manifest's shared-row grouping is structurally sound: exactly
    the 5 framework anchors in order, each mapped to >=1 existing content block,
    no block reused across rows."""
    manifest = json.loads(manifest_path(HERE).read_text(encoding="utf-8"))
    shared = manifest["model"]["sharedRows"]
    assert [r["anchor"] for r in shared] == list(SHARED_ANCHORS)
    seen_blocks: set[str] = set()
    for row in shared:
        assert row["blocks"], f"{row['anchor']} has no content blocks"
        for b in row["blocks"]:
            assert block_path(HERE, b).exists(), f"missing block {b}"
            assert b not in seen_blocks, f"block {b} reused across rows"
            seen_blocks.add(b)
        for key in ("topic", "whenToUse", "routerHint"):
            assert row[key], f"{row['anchor']} missing {key}"


def test_per_model_rows_never_reuse_shared_anchor() -> None:
    """A per-model row must not claim a shared anchor (that would shadow the
    auto-prepended shared row)."""
    for slug in _active_models():
        model = json.loads(model_json_path(HERE, slug).read_text(encoding="utf-8"))
        for r in model["rows"]:
            assert r["anchor"] not in SHARED_ANCHORS, (
                f"{slug} per-model row reuses shared anchor {r['anchor']}"
            )


def test_model_json_route_blocks_are_consistent() -> None:
    """model.json is the single per-model registry: it owns the routing view.
    Every user-facing topic row carries a non-empty ``route:{name,triggers}``;
    the structural rows (model-reference, out-of-scope) carry none; and the route
    ``name`` is intentionally distinct from the row ``topic`` (e.g. "Usage" vs
    "Usage Topic") so neither is ever derived from the other."""
    structural = {"model-reference", "out-of-scope"}
    for slug in _active_models():
        model = json.loads(model_json_path(HERE, slug).read_text(encoding="utf-8"))
        assert model.get("title"), f"{slug} model.json missing title"
        for r in model["rows"]:
            assert "route" in r, (
                f"{slug} row {r['anchor']} must declare 'route' explicitly "
                '(use "route": null for a structural row)'
            )
            route = r.get("route")
            if r["anchor"] in structural:
                assert route is None, f"{slug} structural row {r['anchor']} has a route"
                continue
            assert route, f"{slug} topic row {r['anchor']} missing route block"
            assert route.get("name") and route.get("triggers"), (
                f"{slug} row {r['anchor']} route missing name/triggers"
            )


def test_modelorder_matches_active_models() -> None:
    """modelOrder must contain every on-disk model (a model.json absent from
    modelOrder would deploy yet be invisible to cross-model routing/the thin
    router), and active_models() must return modelOrder filtered to the active
    slugs in declared order. A slug listed in modelOrder without a model.json yet
    is allowed -- it stays inactive until its instructions land (see
    _core.routing.active_models), so this is a subset check, not exact equality."""
    on_disk = {
        d.name for d in models_dir(HERE).iterdir()
        if (d / "model.json").exists()
    }
    order = json.loads((HERE / "routing.json").read_text(encoding="utf-8"))["modelOrder"]
    orphans = on_disk - set(order)
    assert not orphans, f"on-disk models {sorted(orphans)} missing from modelOrder {order}"
    assert _active_models() == [s for s in order if s in on_disk], (
        "active_models() must return modelOrder filtered to active slugs, in order"
    )


def test_load_model_meta_requires_explicit_route(tmp_path: Path) -> None:
    """A content row that omits the ``route`` key fails loud (rather than being
    silently dropped from routing/descriptions). Explicit ``"route": null`` is
    the only way to declare a structural, non-routing row."""
    from _core.routing import load_model_meta

    canon = tmp_path / "instructions"
    d = canon / "models" / "model-a"
    d.mkdir(parents=True)
    (d / "model.json").write_text(json.dumps({
        "slug": "model-a", "title": "Model A",
        "rows": [{"anchor": "forgot-route", "topic": "Oops"}],
    }), encoding="utf-8")

    with _assert_raises(ValueError, "must declare 'route'"):
        load_model_meta(canon, "model-a")


def test_active_models_fails_loud_on_orphan_on_disk_model(tmp_path: Path) -> None:
    """A model.json present on disk but absent from modelOrder would deploy yet be
    invisible to routing — active_models must raise, naming the orphan."""
    from _core.routing import active_models

    canon = tmp_path / "instructions"
    canon.mkdir()
    (canon / "routing.json").write_text(
        json.dumps({"modelOrder": ["model-a"]}), encoding="utf-8"
    )
    for s in ("model-a", "model-b"):
        d = canon / "models" / s
        d.mkdir(parents=True)
        (d / "model.json").write_text(
            json.dumps({"slug": s, "title": s, "rows": []}), encoding="utf-8"
        )

    with _assert_raises(ValueError, "model-b"):
        active_models(canon)


def test_no_literal_id_refs_in_any_row_body() -> None:
    """Cross-references in every authored body must be {{ref:anchor}} tokens, not
    hard-coded `(Id N)` literals (which silently drift when row order changes)."""
    literal = re.compile(r"\(Ids? \d+")
    for path in _all_body_paths():
        text = path.read_text(encoding="utf-8")
        assert not literal.search(text), f"literal (Id N) ref leaked into {path}"


def test_worked_example_anchors_all_resolve() -> None:
    """Every workedExamples anchor must name an assembled row for that model."""
    for slug in _active_models():
        assembled, model = emit_model._assemble(HERE, slug)
        known = {r["anchor"] for r in assembled}
        for ex in model.get("workedExamples", []):
            for anchor in ex["rows"]:
                assert anchor in known, f"{slug} workedExample anchor {anchor} unknown"


def test_cross_model_routing_is_correct() -> None:
    """With PC active, every model's always-on router reroutes to its sibling
    (by title + resolved prod GUID), never to itself, in modelOrder
    order."""
    from _core.routing import load_model_meta

    order = json.loads((HERE / "routing.json").read_text(encoding="utf-8"))["modelOrder"]
    active = _active_models()
    titles = {s: load_model_meta(HERE, s)["title"] for s in active}
    for slug in active:
        router = emit_model.render(HERE, slug, PROD_GUIDS)[
            "Copilot/Instructions/instructions.md"
        ]
        assert "## Other Ask ADIA models" in router, f"{slug} has no reroute section"
        section = router.split("## Other Ask ADIA models", 1)[1]
        # Own GUID never appears in the reroute section (no self-route).
        assert PROD_GUIDS[slug] not in section, f"{slug} self-routes"
        siblings = [s for s in order if s != slug and s in active]
        for sib in siblings:
            assert titles[sib] in section, f"{slug} missing {sib} title"
            assert PROD_GUIDS[sib] in section, f"{slug} missing {sib} GUID"
        # Deterministic order: sibling titles appear in modelOrder order.
        positions = [section.index(titles[s]) for s in siblings]
        assert positions == sorted(positions), f"{slug} reroute order not deterministic"


def test_out_of_scope_row_is_generated_from_topics() -> None:
    """The out-of-scope row is fully generated (no authored file) and is now the
    *slim* version: a model-agnostic deny/reroute decision rule that points back
    at the always-on guidance instead of restating its Topic index or sibling
    list. So the emitted row must NOT duplicate sibling GUIDs (those live only in
    the always-on router), and it must carry no unresolved tokens."""
    # No hand-authored out-of-scope files remain anywhere.
    assert not list(HERE.glob("models/*/rows/out-of-scope.md")), (
        "out-of-scope is generated — delete any models/*/rows/out-of-scope.md"
    )
    for slug in _active_models():
        table = emit_model.render(HERE, slug, PROD_GUIDS)[
            "definition/tables/_COPILOT_INSTRUCTIONS.tmdl"
        ]
        assert "When NOT to Use This Model" in table, f"{slug} missing OOS row"
        # Slim contract: points at the always-on sections instead of restating.
        assert "Topic index" in table, f"{slug} OOS missing Topic-index pointer"
        assert "reroute" in table, f"{slug} OOS missing reroute pointer"
        # Slimming proof: the OOS row no longer re-lists sibling dataset GUIDs
        # (the always-on router owns that list). Only the model's OWN guid may
        # appear elsewhere in the table; no sibling GUID should be in this row.
        oos = table.split("When NOT to Use This Model", 1)[1]
        for sib, guid in PROD_GUIDS.items():
            if sib != slug:
                assert guid not in oos, f"{slug} OOS still restates sibling {sib} GUID"
        assert "{{model-guid:" not in table and "{{ref:" not in table, (
            f"{slug} OOS left unresolved tokens"
        )


def test_emit_is_byte_stable() -> None:
    """Rendering twice in the same process yields identical bytes (no
    dict/order nondeterminism leaking into the golden hash)."""
    for slug in _active_models():
        assert emit_model.render(HERE, slug, PROD_GUIDS) == emit_model.render(HERE, slug, PROD_GUIDS)


def test_routing_map_is_well_formed() -> None:
    """routing.json must declare modelOrder + the shared description config, and
    must NOT carry per-model topic ownership (that lives in each model.json).
    Each model.json must declare a title + at least one route topic, and must
    NOT store a per-model guid: the dataset GUID is derived from the slug as
    {{model-guid:<slug>}} at emit time, so storing it would be redundant (and a
    drift hazard)."""
    from _core.routing import load_model_meta

    routing = json.loads((HERE / "routing.json").read_text(encoding="utf-8"))
    assert "models" not in routing, "routing.json must not carry a per-model block"
    order = routing["modelOrder"]
    assert {"azure-data-insights",
            "azure-data-partner-community"} <= set(order)
    for key in ("descriptionTemplate", "descriptionTopicsSuffix", "descriptionScope"):
        assert routing[key], f"routing.json missing required {key}"
    for slug in _active_models():
        model = json.loads(model_json_path(HERE, slug).read_text(encoding="utf-8"))
        assert model["title"]
        assert "guid" not in model, f"{slug} must not store a redundant guid (derived from slug)"
        meta = load_model_meta(HERE, slug)
        assert meta["topics"]
        for t in meta["topics"]:
            assert t["name"] and t["triggers"]


def test_cross_model_section_lights_up_with_active_sibling(tmp_path: Path) -> None:
    """With a sibling that has a model.json, the section lists it + its guid
    token, and detokenizes cleanly via the model token map."""
    from _core.routing import render_cross_model_section
    from _core.tokens import TokenMap, detokenize, find_tokens

    # Mirror the real layout: canonical_root is the engine dir; per-model
    # overlays are colocated under models/<slug>/ inside it (paths.py resolver).
    canon = tmp_path / "instructions"
    canon.mkdir()
    (canon / "routing.json").write_text(json.dumps({
        "modelOrder": ["model-a", "model-b"],
    }), encoding="utf-8")
    rows = {
        "model-a": [{"anchor": "alpha", "topic": "Alpha Topic",
                     "route": {"name": "Alpha", "triggers": "a, aa"}}],
        "model-b": [{"anchor": "beta", "topic": "Beta Topic",
                     "route": {"name": "Beta", "triggers": "b, bb"}}],
    }
    for s in ("model-a", "model-b"):
        d = canon / "models" / s
        d.mkdir(parents=True)
        (d / "model.json").write_text(
            json.dumps({"slug": s, "title": s.replace("model-", "Model ").title(),
                        "rows": rows[s]}),
            encoding="utf-8",
        )

    section = render_cross_model_section(canon, "model-a")
    assert "Model B" in section and "Model A" not in section
    # The GUID token is derived from the sibling's slug (routing.json stores no
    # guid), so it must still appear and resolve.
    assert "{{model-guid:model-b}}" in section

    resolved = detokenize(section, TokenMap(guids={"model-b": "GUID-B"}, refs={}))
    assert "GUID-B" in resolved
    assert not find_tokens(resolved)


def test_model_description_within_cap_and_lists_topics() -> None:
    """Each model's generated description is <=500 chars and names every topic
    from its model.json (so Copilot grounding stays in sync with trained topics)."""
    from _core.model_description import MAX_DESCRIPTION_LEN, build_description
    from _core.routing import load_model_meta

    for slug in _active_models():
        desc = build_description(HERE, slug)
        assert len(desc) <= MAX_DESCRIPTION_LEN, f"{slug} description over cap"
        for topic in load_model_meta(HERE, slug)["topics"]:
            assert topic["name"] in desc, f"{slug} desc missing topic {topic['name']}"


def test_description_preserves_curated_lead_in_and_is_idempotent() -> None:
    """A hand-authored description is kept as the lead-in with the topics sentence
    appended; a model with none gets the template. Re-feeding either result back is
    a no-op (deploy can re-run without stacking)."""
    from _core.model_description import build_description

    slug = "azure-data-insights"
    curated = "This model covers Azure data analytics."

    combined = build_description(HERE, slug, existing=curated)
    assert combined.startswith(curated + " Trained topics:"), combined
    assert "Usage" in combined
    assert build_description(HERE, slug, existing=combined) == combined  # idempotent

    templated = build_description(HERE, slug, existing=None)
    assert templated.startswith("The definitive source of")
    assert build_description(HERE, slug, existing=templated) == templated  # idempotent


def test_platform_description_roundtrips_with_apply(tmp_path: Path) -> None:
    """read_platform_description recovers exactly what apply_platform_description
    wrote, and apply is idempotent (replaces, never stacks)."""
    import json

    from _core.model_description import (
        apply_platform_description,
        read_platform_description,
        read_platform_display_name,
    )

    pf = tmp_path / ".platform"
    pf.write_text(
        json.dumps({"metadata": {"type": "SemanticModel", "displayName": "Demo"}}, indent=2),
        encoding="utf-8",
    )
    assert read_platform_description(pf) is None
    assert read_platform_display_name(pf) == "Demo"

    apply_platform_description(pf, "First description.")
    assert read_platform_description(pf) == "First description."

    apply_platform_description(pf, "Second description.")
    twice = pf.read_text(encoding="utf-8")
    assert read_platform_description(pf) == "Second description."
    assert "First description." not in twice
    # displayName and other metadata survive untouched.
    data = json.loads(twice)
    assert data["metadata"]["displayName"] == "Demo"
    assert data["metadata"]["type"] == "SemanticModel"


def test_description_ignores_displayname_placeholder() -> None:
    """A .platform description that merely repeats the displayName is treated as no
    curated lead-in, so the model gets the full generated template."""
    from _core.model_description import build_description

    slug = "azure-data-insights"
    templated = build_description(HERE, slug, existing=None)
    placeholder = build_description(
        HERE, slug, existing="Azure Data Insights", display_name="Azure Data Insights"
    )
    assert placeholder == templated, placeholder


def test_router_artifact_matches_generator() -> None:
    """The committed thin-router artifact must equal emit_router.render() byte for
    byte (drift guard for the consumer router deliverable)."""
    import emit_router

    artifact = HERE / emit_router.ARTIFACT_REL
    assert artifact.exists(), "router artifact missing — run emit_router.py --update-golden"
    assert artifact.read_bytes().decode("utf-8") == emit_router.render(HERE), (
        "router artifact is stale — regenerate with emit_router.py --update-golden"
    )


def test_router_is_structurally_complete() -> None:
    """The router must list every active model (GUID as a token) and every one of
    its model.json topics, and must carry no unresolved {{ref:...}} tokens."""
    import emit_router
    from _core.routing import load_model_meta

    rendered = emit_router.render(HERE)
    active = emit_router._active_models(HERE)
    assert set(active) == set(EXPECTED_MODELS), "router active-model set drifted"
    for slug in active:
        model = load_model_meta(HERE, slug)
        assert f"{{{{model-guid:{slug}}}}}" in rendered, f"router missing GUID token for {slug}"
        assert f"### {model['title']}" in rendered, f"router missing section for {slug}"
        for topic in model["topics"]:
            assert f"| {topic['name']} |" in rendered, (
                f"router missing topic {topic['name']} for {slug}"
            )
    # Router owns no per-row cross-references — only model-guid tokens are allowed.
    assert "{{ref:" not in rendered, "router must not contain {{ref:...}} tokens"
    # DAX-only path bootstrap: the router must discover fetch handles from the
    # table itself (SELECTCOLUMNS [Key]) and fetch by the descriptive [Key], never
    # by the LLM-blind ordinal [Id].
    assert "SELECTCOLUMNS(" in rendered and "[Key]" in rendered, (
        "router must bootstrap key discovery via SELECTCOLUMNS([Key]...)"
    )
    assert "[Key] IN" in rendered, "router must fetch rows by [Key]"
    assert "[Id] IN" not in rendered, "router must not fetch rows by ordinal [Id]"


def test_layout_is_split_into_udf_and_instructions() -> None:
    """The framework root must be cleanly split into ``udf/`` and
    ``instructions/`` with no legacy tangled layout left behind."""
    askadia = HERE.parent  # askadia
    # New canonical roots exist.
    assert (askadia / "udf" / "common" / "functions.tmdl").is_file()
    assert (askadia / "udf" / "common" / "askadia_config.json").is_file()
    assert (askadia / "udf" / "common" / "tables").is_dir()
    assert (askadia / "udf" / "models").is_dir()
    assert (common_dir(HERE) / "manifest.json").is_file()
    assert (common_dir(HERE) / "router-preamble.md").is_file()
    # The old top-level locations must no longer exist.
    for stale in (
        askadia / "functions.tmdl",
        askadia / "askadia_config.json",
        askadia / "tables",
        askadia / "models",
        HERE / "content",
    ):
        assert not stale.exists(), f"legacy path still present: {stale}"


def test_instruction_models_are_udf_bootstrapped() -> None:
    """Every instruction-active model must also carry a UDF overlay README (the
    deploy gate). Otherwise its router would advertise a model that
    ``setup_askadia_framework`` never runs for."""
    udf_models = HERE.parent / "udf" / "models"
    for slug in _active_models():
        gate = udf_models / slug / "README.md"
        assert gate.is_file(), f"{slug} has instructions but no UDF gate at {gate}"


def test_udf_bootstrapped_models_have_instructions() -> None:
    """The mirror of the UDF gate: every UDF-bootstrapped model (overlay
    README present) must also have an instruction set (models/<slug>/model.json).
    ``setup_askadia_framework`` enforces this coupling at deploy and fails loud;
    this asserts the on-disk state can't drift in the first place."""
    udf_models = HERE.parent / "udf" / "models"
    for d in udf_models.iterdir():
        if not (d / "README.md").is_file():
            continue
        mj = model_json_path(HERE, d.name)
        assert mj.is_file(), (
            f"{d.name} is UDF-bootstrapped but has no instruction set at {mj}"
        )


def test_deploy_op_canonical_paths_exist() -> None:
    """The UDF deploy ops have no unit tests of their own; assert their canonical
    path constants point at real files/dirs so a missed reorg reference fails
    loudly here instead of at deploy time."""
    import sys

    deploy = HERE.parent / "deploy"
    ops = HERE.parents[1] / "operations"
    for d in (deploy, ops):
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))

    import generate_annotation_config as gac
    import generate_variant_config as gvc
    import merge_shared_scaffold as mss
    import model_overlay as mo

    assert mss.DEFAULT_CANONICAL_PATH.is_file(), mss.DEFAULT_CANONICAL_PATH
    assert mss.DEFAULT_CANONICAL_TABLES_DIR.is_dir(), mss.DEFAULT_CANONICAL_TABLES_DIR
    assert any(mss.DEFAULT_CANONICAL_TABLES_DIR.glob("*.tmdl"))
    assert gac.SHARED_ASKADIA_CONFIG_PATH.is_file(), gac.SHARED_ASKADIA_CONFIG_PATH
    assert gvc.SHARED_ASKADIA_CONFIG_PATH.is_file(), gvc.SHARED_ASKADIA_CONFIG_PATH
    assert mo.OVERLAY_MODELS_DIR.is_dir(), mo.OVERLAY_MODELS_DIR
    assert mo.OVERLAY_MODELS_DIR == HERE.parent / "udf" / "models"
    for slug in _active_models():
        assert mo.resolve_overlay_dir(slug, models_root=mo.OVERLAY_MODELS_DIR).is_dir()


def test_real_config_resolves_for_every_env() -> None:
    """Every deployment environment must resolve an explicit, valid GUID for every
    active model from the REAL config/model_guids.yml — not just prod. The reorg's
    no-fallback design means a typo'd or missing dev/test/prod GUID would
    pass the prod-only checks yet break only at that environment's deploy. This
    exercises the actual centralized config across all envs to catch that early."""
    envs = ("dev", "test", "prod")
    expected = set(EXPECTED_MODELS)
    prod = load_guids(MODEL_GUIDS_YML, "prod")
    for env in envs:
        resolved = load_guids(MODEL_GUIDS_YML, env)
        # Every active model present in every env (load_guids already validates
        # GUID shape + non-empty + required prod baseline, and raises on a gap).
        assert expected <= set(resolved), f"{env} missing GUIDs for {expected - set(resolved)}"
        for slug in expected:
            # A non-prod env that silently reused the prod dataset GUID is exactly
            # the cross-env mistake no-fallback exists to prevent.
            if env != "prod":
                assert resolved[slug] != prod[slug], (
                    f"{env}.{slug} GUID equals prod — likely a copy-paste of the prod dataset"
                )


def test_merge_blocks_replaces_appends_and_preserves() -> None:
    """The UDF splice (merge_shared_scaffold) mutates shipped per-model TMDL at
    deploy and has no other unit coverage. Assert the core contract on the pure
    block functions: canonical blocks REPLACE same-named per-model blocks,
    per-model-only UDFs are PRESERVED, and canonical blocks absent from per-model
    are APPENDED. A regression here silently corrupts deployed model UDFs."""
    import sys

    deploy = HERE.parent / "deploy"
    ops = HERE.parents[1] / "operations"
    for d in (deploy, ops):
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
    import merge_shared_scaffold as mss

    canonical_text = (
        "function 'Local.AskADIA.A' =\n\t1\n\n"
        "function 'Local.AskADIA.B' =\n\t2\n"
    )
    per_model_text = (
        "function 'Local.AskADIA.A' =\n\t99\n\n"
        "function 'Local._RankX' =\n\t7\n"
    )
    canon = mss._parse_blocks(canonical_text, "canon")
    per = mss._parse_blocks(per_model_text, "model")
    r = mss._merge_blocks(canon, per, per_model_text)

    assert r.replaced == ["Local.AskADIA.A"], r.replaced       # canonical wins
    assert r.replaced_changed == ["Local.AskADIA.A"], r.replaced_changed
    assert r.preserved == ["Local._RankX"], r.preserved        # per-model UDF survives
    assert r.appended == ["Local.AskADIA.B"], r.appended       # missing canonical appended
    # Canonical body replaced the per-model body (no stale '99' left).
    assert "function 'Local.AskADIA.A' =\n\t1" in r.output_text
    assert "\t99" not in r.output_text
    # Every UDF that should exist is present exactly once.
    out_names = [b.name for b in mss._parse_blocks(r.output_text, "merged")]
    assert sorted(out_names) == ["Local.AskADIA.A", "Local.AskADIA.B", "Local._RankX"]


def test_dangling_cross_row_anchor_is_caught() -> None:
    """Each row's Instructions is fetched standalone, so a `](#x)` link must target
    a heading in the SAME row; cross-row pointers must be {{ref:}} tokens. The
    {{...}} token guards don't cover raw Markdown anchors -- this guard does. A
    regression reintroduces dead links when a row is read on its own."""
    from _core.anchors import find_dangling_anchors

    # In-row anchor (heading present) -> OK.
    assert find_dangling_anchors("## Setup\nSee [Setup](#setup).") == []
    # Cross-row anchor (no such heading in this body) -> flagged.
    assert find_dangling_anchors("See [Workflow](#workflow) above.") == ["#workflow"]
    # Anchor inside a fenced code block -> ignored (it's an example, not a link).
    fenced = "```md\n[x](#not-a-real-heading)\n```\n# Real\n"
    assert find_dangling_anchors(fenced) == []


if __name__ == "__main__":
    import tempfile

    test_model_emitter_consumes_only_content()
    test_guids_only_in_manifest()
    test_tmdl_codec_roundtrip()
    test_model_emit_resolves_all_tokens()
    test_malformed_token_is_caught_not_shipped()
    with tempfile.TemporaryDirectory() as d:
        test_render_raises_on_malformed_token_in_body(Path(d))
    test_model_does_not_quote_own_guid_anywhere()
    test_sibling_guids_are_env_resolved_in_router()
    test_render_fails_loud_on_missing_guid()
    test_resolve_guids_env_and_validation()
    test_shared_row_grouping_is_well_formed()
    test_per_model_rows_never_reuse_shared_anchor()
    test_no_literal_id_refs_in_any_row_body()
    test_worked_example_anchors_all_resolve()
    test_model_description_within_cap_and_lists_topics()
    test_description_preserves_curated_lead_in_and_is_idempotent()
    test_cross_model_routing_is_correct()
    test_out_of_scope_row_is_generated_from_topics()
    test_emit_is_byte_stable()
    test_routing_map_is_well_formed()
    test_model_json_route_blocks_are_consistent()
    test_modelorder_matches_active_models()
    test_load_model_meta_requires_explicit_route(Path(tempfile.mkdtemp()))
    test_active_models_fails_loud_on_orphan_on_disk_model(Path(tempfile.mkdtemp()))
    test_router_artifact_matches_generator()
    test_router_is_structurally_complete()
    test_description_ignores_displayname_placeholder()
    test_layout_is_split_into_udf_and_instructions()
    test_instruction_models_are_udf_bootstrapped()
    test_udf_bootstrapped_models_have_instructions()
    test_deploy_op_canonical_paths_exist()
    test_real_config_resolves_for_every_env()
    test_merge_blocks_replaces_appends_and_preserves()
    test_dangling_cross_row_anchor_is_caught()
    with tempfile.TemporaryDirectory() as d:
        test_cross_model_section_lights_up_with_active_sibling(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_platform_description_roundtrips_with_apply(Path(d))
    print("All canonical-instructions tests passed.")
