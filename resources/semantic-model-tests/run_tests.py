"""
Run YAML-defined DAX assertions against a Power BI / Microsoft Fabric semantic
model over the XMLA endpoint.

Two modes:
  --model <name>          test a model that is already deployed and refreshed
  --deploy-from <dir>     publish a throwaway copy of a *.SemanticModel/ tree,
                          bind connections, refresh, test it, then delete it

Exit code: 0 = all pass / snapshots updated. 1 = at least one failure. 2 = fatal.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
import tempfile
import time
import traceback
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import yaml

from lib import connections, deploy, refresh, staging
from lib.auth import (
    DEFAULT_FABRIC_API,
    FABRIC_SCOPE,
    PBI_SCOPE,
    Auth,
)

# --- Constants ----------------------------------------------------------------
VALID_CATEGORIES = {"snapshot", "structural", "negative"}
# Unknown keys were silently ignored, so a typo read as a passing test that asserted nothing.
_COMMON_CASE_KEYS = {"id", "category", "dax", "description"}
_STRUCTURAL_KEYS = {
    "expected_columns", "expected_row_count", "contains_any", "contains_all", "contains_none",
}
# Per-category so a key that is valid *somewhere* can't sit inertly on the wrong
# category -- e.g. expected_error_regex on a structural case asserts nothing.
CASE_KEYS_BY_CATEGORY = {
    "structural": _COMMON_CASE_KEYS | _STRUCTURAL_KEYS,
    "negative": _COMMON_CASE_KEYS | {"expected_error_regex"},
    "snapshot": _COMMON_CASE_KEYS,
}
VALID_CASE_KEYS = set().union(*CASE_KEYS_BY_CATEGORY.values())
# Assertion fields that must be lists: a bare string would otherwise be iterated
# character by character, so `contains_none: Error` would test for "E", "r", ...
_LIST_CASE_KEYS = {"expected_columns", "contains_any", "contains_all", "contains_none"}

# The retail.amd64 net45 AdomdClient build is a self-contained managed assembly
# (XMLA over HTTPS; no MSOLAP OLE DB install needed). Downloaded at runtime so
# the repo never vendors a binary. This direct nuget.org GET works in CI.
ADOMD_NUGET_URL = "https://www.nuget.org/api/v2/package/Microsoft.AnalysisServices.AdomdClient.retail.amd64"

# Machine-owned snapshot sidecars live in this subdir next to each catalog file.
SNAPSHOT_DIR_NAME = "__snapshots__"
_SIDECAR_HEADER = (
    "# Generated snapshots -- do not edit by hand.\n"
    "# Recapture with:  python run_tests.py ... --update-snapshots\n"
    "# The hand-authored case definitions live in the sibling .yml file.\n"
)

# CI logs are frequently public. Scrub anything that looks like a credential or a
# connection string before printing an exception or a failure message.
_SENSITIVE_OUTPUT_RE = re.compile(
    r"(Provider=MSOLAP;|Password\s*=|Authorization\s*[:=]|Bearer\s+\S+|powerbi://)",
    re.IGNORECASE,
)


def _redact_sensitive_text(text: object) -> str:
    """Drop any line that looks like it carries a token or connection string."""
    return "\n".join(
        "[redacted potentially sensitive output line]" if _SENSITIVE_OUTPUT_RE.search(line) else line
        for line in str(text).splitlines()
    )


# --- Catalog ------------------------------------------------------------------


@dataclass
class TestCase:
    """
    A single DAX test case loaded from a YAML catalog file.

    Holds the assertion contract (snapshot, structural, or negative) plus
    the DAX expression to execute. ``source_file`` is captured so the matching
    ``__snapshots__/`` sidecar can be located in ``--update-snapshots`` mode.
    """

    id: str
    category: str
    dax: str
    description: str = ""
    expected_snapshot: str | None = None
    expected_columns: list[str] | None = None
    expected_row_count: dict | None = None
    contains_any: list[str] | None = None
    contains_all: list[str] | None = None
    contains_none: list[str] | None = None
    expected_error_regex: str | None = None
    source_file: Path = field(default_factory=Path)


def load_catalog(catalog_dirs: list[Path]) -> list[TestCase]:
    """
    Load test cases from one or more catalog directories.

    Multiple directories let you compose shared and model-specific catalogs in a
    single run. Case IDs must be globally unique across all supplied directories.
    """
    cases: list[TestCase] = []
    seen: set[str] = set()
    for catalog_dir in catalog_dirs:
        if not catalog_dir.exists():
            msg = f"Catalog directory does not exist: {catalog_dir}"
            raise FileNotFoundError(msg)
        for path in sorted(catalog_dir.rglob("*.yml")):
            if SNAPSHOT_DIR_NAME in path.parts:
                continue
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            snaps = load_snapshots(path)
            file_cases: list[TestCase] = []
            for raw in doc.get("cases", []):
                tc = _validate(raw, path, seen)
                if tc.id in snaps:
                    tc.expected_snapshot = snaps[tc.id]
                file_cases.append(tc)
                cases.append(tc)
                seen.add(tc.id)
            orphans = sorted(set(snaps) - {tc.id for tc in file_cases})
            if orphans:
                msg = f"{_sidecar_path(path)}: snapshot ids with no matching case: {orphans}"
                raise ValueError(msg)
    return cases


def _sidecar_path(source_file: Path) -> Path:
    """Path to the machine-owned snapshot sidecar for a catalog source file."""
    return source_file.parent / SNAPSHOT_DIR_NAME / source_file.name


def load_snapshots(source_file: Path) -> dict[str, Any]:
    """Load the {id: expected_snapshot} map from a source file's sidecar."""
    sidecar = _sidecar_path(source_file)
    if not sidecar.exists():
        return {}
    doc = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
    return dict(doc.get("snapshots", {}))


def write_snapshots(source_file: Path, snapshots: dict[str, Any]) -> None:
    """Write the {id: value} map to a source file's sidecar (sorted, LF, header)."""
    sidecar = _sidecar_path(source_file)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: snapshots[k] for k in sorted(snapshots)}
    body = yaml.safe_dump(
        {"snapshots": ordered},
        sort_keys=False,
        default_flow_style=False,
        width=200,
        allow_unicode=True,
    )
    sidecar.write_text(_SIDECAR_HEADER + body, encoding="utf-8", newline="\n")


def _validate(raw: dict, path: Path, seen: set[str]) -> TestCase:
    cid = raw.get("id")
    if not cid:
        msg = f"{path}: case missing 'id'"
        raise ValueError(msg)
    if cid in seen:
        msg = f"{path}: duplicate id {cid!r}"
        raise ValueError(msg)
    # Checked before the unknown-key sweep below so this specific, actionable
    # message wins over a generic "unknown key" for a common mistake.
    if "expected_snapshot" in raw or "expected_value" in raw:
        msg = (
            f"{path}/{cid}: inline 'expected_snapshot'/'expected_value' is not allowed; "
            f"snapshot values live in the __snapshots__/ sidecar (use --update-snapshots)"
        )
        raise ValueError(msg)
    # Reject unknown keys: a misspelled assertion key would otherwise be dropped
    # silently, leaving a case that runs its DAX and asserts nothing.
    unknown = sorted(set(raw) - VALID_CASE_KEYS)
    if unknown:
        msg = f"{path}/{cid}: unknown key(s) {unknown}; valid keys are {sorted(VALID_CASE_KEYS)}"
        raise ValueError(msg)
    cat = raw.get("category")
    if cat not in VALID_CATEGORIES:
        msg = f"{path}/{cid}: category must be one of {VALID_CATEGORIES}"
        raise ValueError(msg)
    # A key valid for another category is just as inert as a typo, so reject it too.
    misplaced = sorted(set(raw) - CASE_KEYS_BY_CATEGORY[cat])
    if misplaced:
        msg = (
            f"{path}/{cid}: key(s) {misplaced} do not apply to a '{cat}' case "
            f"(valid here: {sorted(CASE_KEYS_BY_CATEGORY[cat])})"
        )
        raise ValueError(msg)
    for key in _LIST_CASE_KEYS & set(raw):
        if raw[key] is not None and not isinstance(raw[key], list):
            msg = f"{path}/{cid}: '{key}' must be a list, got {type(raw[key]).__name__}"
            raise ValueError(msg)
    if not raw.get("dax"):
        msg = f"{path}/{cid}: 'dax' is required"
        raise ValueError(msg)
    if cat == "negative" and not raw.get("expected_error_regex"):
        msg = f"{path}/{cid}: negative case requires 'expected_error_regex'"
        raise ValueError(msg)
    # Row-count contract must be coherent (catch copy-paste mistakes at load time).
    rc = raw.get("expected_row_count")
    if rc is not None:
        if not isinstance(rc, dict) or not set(rc) <= {"exact", "min", "max"}:
            msg = f"{path}/{cid}: expected_row_count keys must be a subset of {{exact, min, max}}"
            raise ValueError(msg)
        if "exact" in rc and ("min" in rc or "max" in rc):
            msg = f"{path}/{cid}: expected_row_count cannot combine 'exact' with 'min'/'max'"
            raise ValueError(msg)
        if "min" in rc and "max" in rc and rc["min"] > rc["max"]:
            msg = f"{path}/{cid}: expected_row_count min ({rc['min']}) > max ({rc['max']})"
            raise ValueError(msg)
    if cat == "negative":
        # Structural keys on a negative case are already rejected by the
        # per-category check above; this only validates the regex compiles.
        try:
            re.compile(raw["expected_error_regex"])
        except re.error as exc:
            msg = f"{path}/{cid}: expected_error_regex is not a valid regex: {exc}"
            raise ValueError(msg) from exc
    if "expected_snapshot" in raw or "expected_value" in raw:
        msg = (
            f"{path}/{cid}: inline 'expected_snapshot'/'expected_value' is not allowed; "
            f"snapshot values live in the __snapshots__/ sidecar (use --update-snapshots)"
        )
        raise ValueError(msg)
    return TestCase(
        id=cid,
        category=cat,
        dax=raw["dax"],
        description=raw.get("description", ""),
        expected_columns=raw.get("expected_columns"),
        expected_row_count=raw.get("expected_row_count"),
        contains_any=raw.get("contains_any"),
        contains_all=raw.get("contains_all"),
        contains_none=raw.get("contains_none"),
        expected_error_regex=raw.get("expected_error_regex"),
        source_file=path,
    )


def write_snapshot(case: TestCase, new_value: str) -> None:
    """Write case's captured value into its source file's snapshot sidecar."""
    snaps = load_snapshots(case.source_file)
    snaps[case.id] = new_value
    write_snapshots(case.source_file, snaps)


# --- XMLA execution -----------------------------------------------------------


def _adomd_cache_dir() -> Path:
    """Stable per-user cache dir for the downloaded AdomdClient assembly."""
    return Path(tempfile.gettempdir()) / "semantic-model-tests" / "adomd"


def _ensure_adomd_client() -> Path:
    """
    Download the AdomdClient .NET assembly from NuGet into a per-user cache the
    first time, then reuse it on every later run (nothing binary is vendored).

    The retail.amd64 net45 build speaks XMLA over HTTPS directly, so a single
    managed DLL is all pythonnet needs -- no MSOLAP OLE DB provider install.
    """
    import io
    import zipfile

    cache = _adomd_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    dll_path = cache / "Microsoft.AnalysisServices.AdomdClient.dll"
    if dll_path.exists():
        return dll_path

    print("    Downloading AdomdClient from NuGet (first run; cached afterward)...")
    resp = requests.get(ADOMD_NUGET_URL, timeout=120)
    resp.raise_for_status()
    member = "lib/net45/Microsoft.AnalysisServices.AdomdClient.dll"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        dll_path.write_bytes(zf.read(member))
    print(f"    AdomdClient ready ({dll_path.stat().st_size // 1024} KB, cached at {cache})")
    return dll_path


def _coerce_clr(val):
    """
    Convert a CLR value from the ADOMD reader to a JSON-native Python value.

    pythonnet passes native ``int`` / ``float`` / ``bool`` / ``str`` straight
    through, but a boxed ``System.Decimal`` (Currency / Fixed-Decimal columns)
    and ``System.DateTime`` arrive as CLR wrapper objects -- NOT Python's
    ``decimal.Decimal`` / ``datetime`` -- so an ``isinstance`` check misses them
    and a blanket ``str()`` would (a) stringify a currency measure into
    ``"1234"`` instead of the number ``1234`` and (b) render a date in the
    machine's locale. Handle those two CLR types explicitly so numeric and
    temporal snapshots stay type-stable and machine-independent.
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float, str)):
        return val
    # CLR wrapper types surface with module "System" under pythonnet.
    if type(val).__module__ == "System":
        name = type(val).__name__
        if name == "Decimal":
            # float() on a CLR Decimal raises; go via its exact string form.
            return float(str(val))
        if name in ("DateTime", "DateTimeOffset"):
            # Invariant ISO 8601 so a date snapshot doesn't shift with locale.
            from System.Globalization import CultureInfo

            return val.ToString("o", CultureInfo.InvariantCulture)
    return str(val)


def _exec_one_xmla(conn, case: TestCase) -> dict:
    """Run a single DAX query on an open AdomdConnection -> result contract."""
    try:
        cmd = conn.CreateCommand()
        cmd.CommandText = case.dax.strip()
        reader = cmd.ExecuteReader()
        try:
            field_count = reader.FieldCount
            columns = [reader.GetName(i) for i in range(field_count)]
            rows: list[dict] = []
            while reader.Read():
                row = {
                    columns[i]: (None if reader.IsDBNull(i) else _coerce_clr(reader.GetValue(i)))
                    for i in range(field_count)
                }
                rows.append(row)
            return {"ok": True, "rows": rows, "columns": columns, "error": None}
        finally:
            reader.Close()
    except Exception as exc:
        # DAX execution errors land here (expected for negative tests).
        return {"ok": False, "rows": [], "columns": [], "error": {"message": str(exc)}}


def run_cases_xmla(
    cases: list[TestCase],
    *,
    model_name: str,
    fabric_api: str,
    workspace_id: str,
    xmla_endpoint: str,
    auth: Auth,
) -> dict[str, dict]:
    """
    Execute DAX cases against the Power BI XMLA endpoint via AdomdClient.

    Loads the net45 AdomdClient assembly in-process with pythonnet (no C#
    source compiled, no out-of-proc exe) and runs one query per case for
    error isolation. XMLA only needs workspace access + a PBI bearer token --
    it is NOT gated by the "Dataset Execute Queries REST API" tenant setting,
    so it works for the service-principal caller that REST executeQueries
    rejects.
    """
    results: dict[str, dict] = {}

    try:
        adomd_dll = _ensure_adomd_client()

        # Force the .NET Framework CLR before importing clr: the net45
        # AdomdClient assembly targets .NET Framework, which is present on the
        # Windows agent (and locally). load() MUST precede `import clr`.
        import pythonnet

        pythonnet.load("netfx")
        import clr  # pythonnet.load("netfx") above must run before this import

        clr.AddReference(str(adomd_dll))
        from Microsoft.AnalysisServices.AdomdClient import AdomdConnection

        # The XMLA Data Source needs the workspace DISPLAY NAME (not the GUID).
        resp = requests.get(
            f"{fabric_api}/v1/workspaces/{workspace_id}",
            headers=auth.headers(FABRIC_SCOPE),
            timeout=30,
        )
        resp.raise_for_status()
        workspace_name = resp.json()["displayName"]

        # User ID=; + Persist Security Info + Impersonation Level let MSOLAP
        # treat Password as a pre-acquired bearer token.
        pbi_token = auth.token(PBI_SCOPE)
        encoded_ws = urllib.parse.quote(workspace_name)
        data_source = f"powerbi://{xmla_endpoint}/v1.0/myorg/{encoded_ws}"
        conn_str = (
            f"Provider=MSOLAP;Data Source={data_source};"
            f"User ID=;Password={pbi_token};"
            f"Persist Security Info=True;Impersonation Level=Impersonate;"
            f"Initial Catalog={model_name}"
        )

        print(f"==> AdomdClient XMLA batch: {len(cases)} queries")
        conn = AdomdConnection(conn_str)
        try:
            conn.Open()
            for c in cases:
                results[c.id] = _exec_one_xmla(conn, c)
        finally:
            conn.Close()
    except Exception as exc:
        # A connection-level failure (AdomdClient download, CLR load, workspace
        # lookup, or Open()) is an INFRA failure, not a test failure. Raise so the
        # top-level handler exits 2 -- a CI gate can then tell "the harness broke"
        # (exit 2) apart from "the model regressed" (exit 1). Per-query DAX errors
        # are isolated inside _exec_one_xmla and never reach here.
        msg = f"XMLA connection failed: {exc}"
        raise RuntimeError(msg) from exc

    return results

# --- Assertions ---------------------------------------------------------------


def assert_case(case: TestCase, result: dict) -> tuple[bool, str]:
    """Dispatch on `case.category`; return (passed, message)."""
    if case.category == "snapshot":
        return _assert_snapshot(case, result)
    if case.category == "structural":
        return _assert_structural(case, result)
    if case.category == "negative":
        return _assert_negative(case, result)
    return False, f"unknown category {case.category!r}"


def _result_snapshot(result: dict) -> str:
    """
    Serialize a DAX result to a stable, type-preserving snapshot string.

    One JSON serialization for every shape, so a type change is caught rather
    than hidden by ``str()`` -- the text ``"None"`` no longer collides with a
    BLANK, and the integer ``240`` no longer collides with the string ``"240"``:

    - 1 row x 1 col -> the bare typed cell value:  ``240`` / ``null`` / ``"Hardware"``
    - any other shape (including 0 rows) -> the JSON array of row objects with
      sorted keys, e.g. ``[{"Product[Category]": "Hardware", "[Total Amount]": 4560}]``
      or ``[]`` for an empty result.

    Row order is significant for table snapshots -- use a deterministic
    ``ORDER BY`` in the DAX so the captured value is stable across runs.
    """
    rows, cols = result["rows"], result["columns"]
    if len(rows) == 1 and len(cols) == 1:
        return json.dumps(rows[0].get(cols[0]), ensure_ascii=False)
    return json.dumps(rows, ensure_ascii=False, sort_keys=True)


def _assert_snapshot(case: TestCase, result: dict) -> tuple[bool, str]:
    if not result["ok"]:
        return False, f"query failed: {result['error']['message']}"
    if case.expected_snapshot is None:
        return False, "no snapshot captured (use --update-snapshots)"
    actual = _result_snapshot(result)
    if actual == case.expected_snapshot:
        return True, "snapshot match"
    return False, _diff(case.expected_snapshot, actual)


def _column_label(col: str) -> str:
    """
    Human-readable column label for `contains_*` matching.

    XMLA returns bare measures as `[Total Amount]` and grouped columns as
    `Product[Category]`. Only unwrap when the WHOLE name is bracketed -- a
    blanket strip('[]') would turn `Product[Category]` into `Product[Category`.
    """
    m = re.fullmatch(r"\[(.*)\]", col)
    return m.group(1) if m else col


def _assert_structural(case: TestCase, result: dict) -> tuple[bool, str]:
    if not result["ok"]:
        return False, f"query failed: {result['error']['message']}"
    rows, cols = result["rows"], result["columns"]
    fail: list[str] = []
    # Column check: skip only when XMLA returned no rows and no column metadata
    if case.expected_columns and (rows or cols):
        missing = set(case.expected_columns) - set(cols)
        if missing:
            fail.append(f"missing columns: {sorted(missing)}")
    if case.expected_row_count:
        rc, n = case.expected_row_count, len(rows)
        if "exact" in rc and n != rc["exact"]:
            fail.append(f"row count {n} != exact {rc['exact']}")
        if "min" in rc and n < rc["min"]:
            fail.append(f"row count {n} < min {rc['min']}")
        if "max" in rc and n > rc["max"]:
            fail.append(f"row count {n} > max {rc['max']}")
    if case.contains_any or case.contains_all or case.contains_none:
        # Two views of the result. Bare needles match values only (so a needle
        # can't be satisfied by a column *name*); a needle written as
        # "Column: value" matches the labelled view, which targets one column.
        flat_values = "\n".join(str(r[c]) for r in rows for c in cols if r.get(c) is not None)
        flat_labelled = "\n".join(
            f"{_column_label(c)}: {r[c]}" for r in rows for c in cols if r.get(c) is not None
        )

        def matches(needle: object) -> bool:
            # Needles come from YAML and may parse as ints (unquoted
            # `contains_any: [1000]`), so compare their string form.
            n = str(needle)
            return n in flat_labelled if ": " in n else n in flat_values

        if case.contains_any and not any(matches(n) for n in case.contains_any):
            fail.append(f"contains_any {case.contains_any} matched none")
        if case.contains_all:
            for needle in case.contains_all:
                if not matches(needle):
                    fail.append(f"contains_all missing {needle!r}")
        if case.contains_none:
            for needle in case.contains_none:
                if matches(needle):
                    fail.append(f"contains_none matched {needle!r}")
    if fail:
        return False, " | ".join(fail)
    return True, f"{len(rows)} rows, {len(cols)} cols OK"


def _assert_negative(case: TestCase, result: dict) -> tuple[bool, str]:
    if result["ok"]:
        return False, "expected query to fail but it succeeded"
    msg = result["error"]["message"] or ""
    if re.search(case.expected_error_regex, msg, re.IGNORECASE):
        return True, f"matched: {case.expected_error_regex}"
    return False, f"error did not match {case.expected_error_regex!r}; got: {msg[:300]}"


def _diff(expected: str, actual: str, max_lines: int = 30) -> str:
    diff = list(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile="expected",
            tofile="actual",
            n=2,
        )
    )
    if len(diff) > max_lines:
        diff = diff[:max_lines] + [f"... ({len(diff) - max_lines} more lines)\n"]
    return "snapshot mismatch:\n" + "".join(diff)


# --- CLI / orchestration ------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    p = argparse.ArgumentParser(
        description="Run YAML-defined DAX assertions against a Power BI / Fabric semantic model over XMLA.",
    )
    p.add_argument("--workspace-id", required=True, help="Target Fabric workspace GUID.")
    p.add_argument(
        "--model",
        help="Display name of an already-deployed semantic model to test. "
        "Mutually exclusive with --deploy-from.",
    )
    p.add_argument(
        "--deploy-from",
        type=Path,
        help="Path to a source *.SemanticModel/ directory. Stages a renamed copy, publishes it "
        "as a throwaway, tests it, and ALWAYS deletes it. Mutually exclusive with --model.",
    )
    p.add_argument(
        "--connection-id",
        action="append",
        default=[],
        metavar="GUID",
        help="Connection to bind to the throwaway before refreshing (repeatable). "
        "Required for DirectLake, which cannot refresh unbound. The connection must "
        "already exist in Fabric and the caller needs 'Use' on it. Only with --deploy-from.",
    )
    p.add_argument(
        "--refresh-type",
        default="Calculate",
        choices=["Calculate", "Full", "DataOnly", "Automatic", "None"],
        help="Refresh to run after publishing. 'Calculate' (default) suits DirectLake; "
        "Import needs 'Full' to load data. 'None' skips the refresh. Only with --deploy-from.",
    )
    p.add_argument(
        "--refresh-timeout",
        type=int,
        metavar="SECONDS",
        help="Override the refresh poll ceiling (default: 240s for Calculate, 1200s for Full). "
        "Raise it for a large Import model. Only with --deploy-from.",
    )
    p.add_argument(
        "--environment",
        default="dev",
        help="Environment name passed to fabric-cicd, selecting which parameter.yml value "
        "set applies. Only meaningful if the source model has a parameter.yml. "
        "Only with --deploy-from.",
    )
    p.add_argument(
        "--keep-model",
        action="store_true",
        help="Skip teardown of the throwaway model (debugging). Only with --deploy-from.",
    )
    p.add_argument(
        "--keep-rls",
        action="store_true",
        help="Keep RLS roles in the staged copy. By default roles are stripped, since a "
        "service principal is rarely a member of any role. Only with --deploy-from.",
    )
    p.add_argument(
        "--catalog-dir",
        required=True,
        type=Path,
        nargs="+",
        help="One or more catalog directories. Cases from all dirs are merged; case IDs must be globally unique.",
    )
    p.add_argument("--api-root", default=DEFAULT_FABRIC_API)
    p.add_argument(
        "--xmla-endpoint",
        default="api.powerbi.com",
        help="XMLA endpoint hostname for AdomdClient (default: api.powerbi.com).",
    )
    p.add_argument(
        "--update-snapshots",
        action="store_true",
        help="Capture current results into the __snapshots__/ sidecars instead of asserting.",
    )
    p.add_argument(
        "--interactive-auth",
        action="store_true",
        help="Use InteractiveBrowserCredential (local browser sign-in) instead of AzureCliCredential.",
    )
    p.add_argument("--filter", help="Only run cases whose id contains this substring.")
    args = p.parse_args()

    if bool(args.model) == bool(args.deploy_from):
        p.error("supply exactly one of --model (test a deployed model) or --deploy-from (publish a throwaway)")
    deploy_only = {
        "--connection-id": args.connection_id,
        "--refresh-type": args.refresh_type != "Calculate",
        "--refresh-timeout": args.refresh_timeout is not None,
        "--environment": args.environment != "dev",
        "--keep-model": args.keep_model,
        "--keep-rls": args.keep_rls,
    }
    if args.model:
        stray = sorted(flag for flag, used in deploy_only.items() if used)
        if stray:
            p.error(f"{', '.join(stray)} only applies with --deploy-from")
    return args


def _load_cases_or_exit(args: argparse.Namespace) -> list[TestCase]:
    """Load + filter cases and validate snapshots up front. Raises SystemExit(2) on fatal."""
    cases = load_catalog(args.catalog_dir)
    if args.filter:
        cases = [c for c in cases if args.filter in c.id]
    if args.update_snapshots:
        cases = [c for c in cases if c.category == "snapshot"]
    if not cases:
        print(f"No cases matched (catalog={args.catalog_dir}, filter={args.filter!r})", file=sys.stderr)
        raise SystemExit(2)
    if not args.update_snapshots:
        missing = [c.id for c in cases if c.category == "snapshot" and c.expected_snapshot is None]
        if missing:
            print(
                f"==> {len(missing)} snapshot case(s) have no captured value; rerun "
                f"with --update-snapshots to (re)capture: {', '.join(missing)}",
                file=sys.stderr,
            )
            raise SystemExit(2)
    return cases


def _run_and_collect(
    cases: list[TestCase],
    *,
    model_name: str,
    workspace_id: str,
    fabric_api: str,
    xmla_endpoint: str,
    auth: Auth,
    update_snapshots: bool,
) -> list[tuple[TestCase, bool, str]]:
    """Run every case over XMLA, then assert (or capture snapshots). Returns result tuples."""
    results: list[tuple[TestCase, bool, str]] = []
    print(f"==> Running {len(cases)} case(s) via AdomdClient (XMLA)")
    t0 = time.time()
    dax_results = run_cases_xmla(
        cases,
        model_name=model_name,
        fabric_api=fabric_api,
        workspace_id=workspace_id,
        xmla_endpoint=xmla_endpoint,
        auth=auth,
    )
    print(f"==> All queries complete in {time.time() - t0:.1f}s")
    for case in cases:
        result = dax_results.get(
            case.id,
            {"ok": False, "rows": [], "columns": [], "error": {"message": "no result from runner"}},
        )
        try:
            if update_snapshots:
                if result["ok"]:
                    snap_str = _result_snapshot(result)
                    write_snapshot(case, snap_str)
                    passed, msg = True, f"snapshot updated ({len(snap_str)} chars)"
                else:
                    passed, msg = False, f"could not capture snapshot: {result['error']['message']}"
            else:
                passed, msg = assert_case(case, result)
        except Exception as exc:
            passed, msg = False, f"runner exception: {_redact_sensitive_text(exc)}"
        results.append((case, passed, msg))
    return results


def _finish(results: list[tuple[TestCase, bool, str]], update_snapshots: bool) -> int:
    """Print the summary and return the process exit code."""
    _print_summary(results)
    if update_snapshots:
        print(
            "==> NOTE: snapshot sidecars were (re)written; review the diff before "
            "committing -- a changed snapshot is a real behavior change to vet.",
        )
    fails = sum(1 for _, p, _ in results if not p)
    return 1 if fails else 0

def run_suite(args: argparse.Namespace) -> int:
    """Load the catalog, run every case over XMLA, assert (or capture snapshots)."""
    cases = _load_cases_or_exit(args)
    auth = Auth(interactive=args.interactive_auth)
    auth.warm()
    fabric_api = args.api_root.rstrip("/")
    print(f"==> Model:      {args.model}")
    print(f"==> Workspace:  {args.workspace_id}")
    print(f"==> Cases:      {len(cases)} from {len(args.catalog_dir)} dir(s)")
    results = _run_and_collect(
        cases,
        model_name=args.model,
        workspace_id=args.workspace_id,
        fabric_api=fabric_api,
        xmla_endpoint=args.xmla_endpoint,
        auth=auth,
        update_snapshots=args.update_snapshots,
    )
    return _finish(results, args.update_snapshots)


def run_suite_ephemeral(args: argparse.Namespace) -> int:
    """
    Publish a throwaway copy of a model, test it, and always tear it down.

    Load the catalog first so a bad case file fails before anything is deployed.
    Teardown lives in a `finally` so a failed assertion, a failed refresh, or a
    crash still can't leak a stray model into the workspace.
    """
    cases = _load_cases_or_exit(args)
    auth = Auth(interactive=args.interactive_auth)
    auth.warm()
    fabric_api = args.api_root.rstrip("/")

    source_dir = args.deploy_from.resolve()
    source_name = source_dir.name.removesuffix(".SemanticModel")
    test_model_name = staging.make_test_model_name("TEST", source_name)
    print(f"==> Source:     {source_dir}")
    print(f"==> Throwaway:  {test_model_name}")
    print(f"==> Workspace:  {args.workspace_id}")
    print(f"==> Cases:      {len(cases)} from {len(args.catalog_dir)} dir(s)")

    model_id: str | None = None
    staging_dir: Path | None = None
    results: list[tuple[TestCase, bool, str]] = []
    teardown_ok = True
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix="smt-stage-"))
        staging.stage_model(
            source_dir=source_dir,
            model_name=test_model_name,
            output_dir=staging_dir,
            strip_rls=not args.keep_rls,
        )
        # A parameter.yml sits beside the model dir, not inside it. Carry it over
        # so fabric-cicd's find/replace still fires against the staged copy.
        source_parameter_yml = source_dir.parent / "parameter.yml"
        if source_parameter_yml.exists():
            shutil.copy2(source_parameter_yml, staging_dir / "parameter.yml")

        print("==> Publishing throwaway")
        deploy.publish_staged_model(
            staging_dir=staging_dir,
            workspace_id=args.workspace_id,
            fabric_api_root=fabric_api,
            token_credential=auth.cred,
            environment=args.environment,
        )

        model_id = connections.resolve_item_id(
            fabric_api=fabric_api,
            workspace_id=args.workspace_id,
            display_name=test_model_name,
            item_type="SemanticModel",
            auth=auth,
        )
        if not model_id:
            msg = f"{test_model_name} not found in the workspace after publish"
            raise RuntimeError(msg)
        print(f"==> Model id:   {model_id}")
        if args.connection_id:
            n = connections.bind_connections(
                fabric_api=fabric_api,
                workspace_id=args.workspace_id,
                model_id=model_id,
                connection_ids=args.connection_id,
                auth=auth,
            )
            print(f"==> Bound {n} connection(s)")

        if args.refresh_type != "None":
            t0 = time.time()
            refresh.refresh_model(
                workspace_id=args.workspace_id,
                fabric_api=fabric_api,
                auth=auth,
                dataset_id=model_id,
                refresh_type=args.refresh_type,
                poll_timeout_sec=args.refresh_timeout,
            )
            print(f"==> Refresh complete in {time.time() - t0:.1f}s")

        results = _run_and_collect(
            cases,
            model_name=test_model_name,
            workspace_id=args.workspace_id,
            fabric_api=fabric_api,
            xmla_endpoint=args.xmla_endpoint,
            auth=auth,
            update_snapshots=args.update_snapshots,
        )
    finally:
        if staging_dir and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if not args.keep_model:
            # Re-resolve when publish created the item but we never captured its
            # id (publish raised late, or the list call was eventually consistent).
            # The name is unique per run, so anything under it belongs to this run.
            if model_id is None:
                for attempt in range(3):
                    if attempt:
                        time.sleep(10)
                    try:
                        model_id = connections.resolve_item_id(
                            fabric_api=fabric_api,
                            workspace_id=args.workspace_id,
                            display_name=test_model_name,
                            item_type="SemanticModel",
                            auth=auth,
                        )
                        if model_id:
                            print(f"==> Teardown:   recovered orphan {test_model_name} ({model_id})")
                            break
                    except Exception as exc:
                        print(f"==> Teardown lookup failed: {_redact_sensitive_text(exc)}", file=sys.stderr)
            if model_id:
                try:
                    teardown_ok = connections.delete_model(
                        fabric_api=fabric_api,
                        workspace_id=args.workspace_id,
                        model_id=model_id,
                        auth=auth,
                    )
                except Exception as exc:
                    teardown_ok = False
                    print(f"==> Teardown error: {_redact_sensitive_text(exc)}", file=sys.stderr)
                if teardown_ok:
                    print("==> Teardown:   deleted")
                else:
                    print(
                        f"==> Teardown:   FAILED -- delete {test_model_name} ({model_id}) manually",
                        file=sys.stderr,
                    )
        elif model_id:
            print(f"==> --keep-model: leaving {test_model_name} ({model_id}) in the workspace")

    # A leaked model is an infra failure, not a test result: surface it as exit 2
    # so a CI gate can't report success while leaving an item behind.
    if not teardown_ok and not args.keep_model:
        return 2
    return _finish(results, args.update_snapshots)


def main() -> int:
    """Run the suite. Returns 0=pass, 1=failures, 2=fatal (infra/setup)."""
    args = parse_args()
    try:
        return run_suite_ephemeral(args) if args.deploy_from else run_suite(args)
    except SystemExit:
        # Explicit fatal paths (e.g. no cases / uncaptured snapshots) already carry
        # their own exit code (2) -- let them through unchanged.
        raise
    except Exception as exc:
        # Setup/infra errors (bad --catalog-dir, missing az login, XMLA connect, ...)
        # are fatal, NOT assertion failures. Exit 2 so a CI gate can distinguish
        # "the harness/infra broke" from "the model regressed" (exit 1).
        # Redacted: an XMLA connect failure can echo the connection string.
        print(f"==> FATAL: {_redact_sensitive_text(exc)}", file=sys.stderr)
        print(_redact_sensitive_text(traceback.format_exc()), file=sys.stderr)
        return 2


def _print_summary(results: Iterable[tuple[TestCase, bool, str]]) -> None:
    results = list(results)
    passed = sum(1 for _, p, _ in results if p)
    failed = len(results) - passed
    print()
    print("=" * 80)
    print(f"  {len(results)} run, {passed} passed, {failed} failed")
    print("=" * 80)
    for case, ok, msg in results:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {case.category:11s} {case.id}")
        if not ok:
            # Redact here rather than at each failure site: this is the single
            # boundary every assertion message flows through on its way to a
            # (frequently public) CI log, and a raw ADOMD error can echo the
            # connection string -- which carries the bearer token.
            for line in _redact_sensitive_text(msg).splitlines() or [msg]:
                print(f"           {line}")


if __name__ == "__main__":
    sys.exit(main())
