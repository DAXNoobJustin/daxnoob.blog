"""
Offline tests for the snapshot-sidecar catalog loader.

Run with:  python -m pytest test_catalog.py     (from semantic_model_tests/)
or:        python test_catalog.py                (no pytest needed)

These exercise run_tests.load_catalog / load_snapshots / write_snapshots against
throwaway temp catalogs. No Fabric auth or deploy -- they lock the machine-owned
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
