"""
Offline tests for the snapshot-sidecar catalog loader.

Run with:  python -m pytest test_catalog.py     (from this directory)
or:        python test_catalog.py                (no pytest needed)

These exercise run_tests.load_catalog / load_snapshots / write_snapshots against
throwaway temp catalogs. No Fabric auth needed; they lock the machine-owned
``__snapshots__/`` sidecar contract so a refactor can't silently break it.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_tests


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _catalog(tmp: Path, cases_yaml: str, snapshots: dict | None = None) -> Path:
    """Write a source catalog file (+ optional sidecar) and return the catalog dir."""
    src = tmp / "sample.yml"
    _write(src, cases_yaml)
    if snapshots is not None:
        run_tests.write_snapshots(src, snapshots)
    return tmp


_SNAP_AND_STRUCT = """\
cases:
  - id: snap_a
    category: snapshot
    dax: "EVALUATE { 1 }"
  - id: struct_b
    category: structural
    dax: "EVALUATE { 2 }"
    expected_columns: ["[Value]"]
"""


def test_load_catalog_merges_sidecar_values():
    """A snapshot case picks up its value from the sibling sidecar."""
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), _SNAP_AND_STRUCT, {"snap_a": "hello"})
        cases = run_tests.load_catalog([cat])
        by_id = {c.id: c for c in cases}
        assert by_id["snap_a"].expected_snapshot == "hello"
        assert by_id["struct_b"].category == "structural"


def test_missing_sidecar_value_loads_as_none():
    """A snapshot case with no sidecar entry loads with expected_snapshot None."""
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), _SNAP_AND_STRUCT, {})  # empty sidecar
        cases = run_tests.load_catalog([cat])
        assert {c.id: c.expected_snapshot for c in cases}["snap_a"] is None


def test_inline_expected_snapshot_rejected():
    """Inline expected_snapshot in source YAML is rejected by the loader."""
    inline = _SNAP_AND_STRUCT.replace(
        '    dax: "EVALUATE { 1 }"',
        '    dax: "EVALUATE { 1 }"\n    expected_snapshot: "inline-not-allowed"',
    )
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), inline)
        _expect_value_error(cat, "expected_snapshot")


def test_inline_expected_value_rejected():
    """Inline expected_value (the removed legacy field) is rejected."""
    inline = _SNAP_AND_STRUCT.replace(
        '    dax: "EVALUATE { 1 }"',
        '    dax: "EVALUATE { 1 }"\n    expected_value: 5',
    )
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), inline)
        _expect_value_error(cat, "expected_value")


def test_orphan_sidecar_id_raises():
    """A sidecar id with no matching source case raises."""
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), _SNAP_AND_STRUCT, {"snap_a": "hi", "ghost_id": "x"})
        _expect_value_error(cat, "ghost_id")


def test_write_then_load_snapshots_roundtrips_sorted():
    """write_snapshots emits a sorted, LF, headed sidecar that load_snapshots reads back."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "sample.yml"
        _write(src, _SNAP_AND_STRUCT)
        run_tests.write_snapshots(src, {"b": "2", "a": "1"})
        sidecar = run_tests._sidecar_path(src)
        raw = sidecar.read_text(encoding="utf-8")
        assert raw.startswith("# Generated snapshots")  # header present
        assert "\r\n" not in raw  # LF only
        assert raw.index("a:") < raw.index("b:")  # sorted by id
        assert run_tests.load_snapshots(src) == {"a": "1", "b": "2"}


def test_result_snapshot_is_type_preserving():
    """Scalars serialize to bare typed JSON, tables to a JSON array -- so a type
    change is caught, not hidden by str() (BLANK vs the text "None", int vs str)."""

    def r(rows, cols):
        return {"ok": True, "rows": rows, "columns": cols, "error": None}

    assert run_tests._result_snapshot(r([{"[Value]": 240}], ["[Value]"])) == "240"
    assert run_tests._result_snapshot(r([{"[Value]": None}], ["[Value]"])) == "null"
    assert run_tests._result_snapshot(r([{"[Value]": "None"}], ["[Value]"])) == '"None"'
    assert run_tests._result_snapshot(r([{"[Value]": True}], ["[Value]"])) == "true"
    assert run_tests._result_snapshot(r([], [])) == "[]"
    # BLANK (null) and the text "None" must NOT collide (the old str() bug).
    assert run_tests._result_snapshot(r([{"[Value]": None}], ["[Value]"])) != run_tests._result_snapshot(
        r([{"[Value]": "None"}], ["[Value]"])
    )


def test_numeric_contains_needle_does_not_crash():
    """An unquoted numeric contains_any/contains_all needle (YAML parses it as int)
    is matched by its string form, not a TypeError."""
    r = {"ok": True, "rows": [{"[Rev]": 1234.0}], "columns": ["[Rev]"], "error": None}
    ok_any, _ = run_tests._assert_structural(
        run_tests.TestCase(id="a", category="structural", dax="E", contains_any=[1234]), r
    )
    ok_all, _ = run_tests._assert_structural(
        run_tests.TestCase(id="b", category="structural", dax="E", contains_all=[1234]), r
    )
    assert ok_any and ok_all


def test_unknown_case_key_rejected():
    """A misspelled assertion key must raise, not be silently dropped -- otherwise
    the case runs its DAX and asserts nothing while reporting PASS."""
    typo = """\
cases:
  - id: typo_case
    category: structural
    dax: "EVALUATE { 1 }"
    expected_row_counts: { exact: 1 }
"""
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), typo)
        _expect_value_error(cat, "expected_row_counts")


def test_contains_none_asserts_absence():
    """contains_none fails when the needle IS present and passes when it isn't."""
    r = {"ok": True, "rows": [{"[Status]": "Error"}], "columns": ["[Status]"], "error": None}
    present, _ = run_tests._assert_structural(
        run_tests.TestCase(id="a", category="structural", dax="E", contains_none=["Error"]), r
    )
    absent, _ = run_tests._assert_structural(
        run_tests.TestCase(id="b", category="structural", dax="E", contains_none=["Fatal"]), r
    )
    assert not present
    assert absent


def test_contains_matching_is_column_scoped():
    """A 'Column: value' needle targets one column; a bare needle matches values
    only, so it can't be satisfied by a column NAME."""
    r = {
        "ok": True,
        "rows": [{"[Region]": "East", "Product[Category]": "Widget"}],
        "columns": ["[Region]", "Product[Category]"],
        "error": None,
    }

    def structural(**kw):
        return run_tests._assert_structural(
            run_tests.TestCase(id="x", category="structural", dax="E", **kw), r
        )[0]

    # Qualified needles target their own column.
    assert structural(contains_all=["Region: East"])
    assert not structural(contains_all=["Region: Widget"])
    # Table-qualified column names must not be mangled by bracket stripping.
    assert structural(contains_all=["Product[Category]: Widget"])
    # A bare needle matches values, never a column name.
    assert structural(contains_any=["East"])
    assert not structural(contains_any=["Region"])
    assert structural(contains_none=["Region"])


def test_column_label_only_unwraps_fully_bracketed_names():
    """strip('[]') would turn 'Product[Category]' into 'Product[Category'."""
    assert run_tests._column_label("[Total Amount]") == "Total Amount"
    assert run_tests._column_label("Product[Category]") == "Product[Category]"
    assert run_tests._column_label("Sales[Amount]") == "Sales[Amount]"


def test_key_from_other_category_rejected():
    """A key that is valid elsewhere is as inert as a typo, so reject it too."""
    misplaced = """\
cases:
  - id: struct_with_error_regex
    category: structural
    dax: "EVALUATE { 1 }"
    expected_error_regex: "boom"
"""
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), misplaced)
        _expect_value_error(cat, "expected_error_regex")


def test_scalar_list_field_rejected():
    """`contains_none: Error` would be iterated character by character."""
    scalar = """\
cases:
  - id: scalar_needle
    category: structural
    dax: "EVALUATE { 1 }"
    contains_none: Error
"""
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), scalar)
        _expect_value_error(cat, "must be a list")


def test_negative_case_cannot_carry_contains_none():
    """A negative case only checks the error, so structural keys must be rejected."""
    mixed = """\
cases:
  - id: neg_case
    category: negative
    dax: "EVALUATE { [Nope] }"
    expected_error_regex: "cannot be determined"
    contains_none: ["boom"]
"""
    with tempfile.TemporaryDirectory() as d:
        cat = _catalog(Path(d), mixed)
        _expect_value_error(cat, "contains_none")


def test_redaction_scrubs_connection_string_lines():
    """A leaked connection string or bearer token must not reach a CI log."""
    text = "line one\nProvider=MSOLAP;Data Source=powerbi://api.powerbi.com/v1.0/myorg/ws\nline three"
    out = run_tests._redact_sensitive_text(text)
    assert "MSOLAP" not in out
    assert "powerbi://" not in out
    assert "line one" in out
    assert "line three" in out


def _expect_value_error(catalog_dir: Path, needle: str) -> None:
    raised: str | None = None
    try:
        run_tests.load_catalog([catalog_dir])
    except ValueError as exc:
        raised = str(exc)
    assert raised is not None, f"expected ValueError mentioning {needle!r}, none raised"
    assert needle in raised, f"expected {needle!r} in error, got: {raised}"


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(fns)} run, {len(fns) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
