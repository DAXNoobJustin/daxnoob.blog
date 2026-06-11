"""
AskADIA semantic-model test runner -- single-file edition.

What it does (in order):
  1. Load YAML test cases from --catalog-dir
  2. Stage source semantic model into a temp dir, rewrite displayName + logicalId,
     strip RLS roles (SP can't satisfy role membership)
  3. Run the FULL prod preprocess chain via process_orchestrator.DeploymentPipeline:
     validate_item, the time-intel + measure-description CSX, setup_askadia_framework
     (which internally merges the shared scaffold and runs all the AskADIA metadata
     generators), then generate_copilot_schema. Same chain as deploy_workspace.py and
     debug_deploy.py -- the test runner does NOT maintain a parallel script list.
  4. Publish throwaway DEBUG_UnitTest_<slug>_<id> model via the pipeline's
     publish_all_items invocation (auto-refresh in YAML post_process is suppressed
     so we can bind connections first; DirectLake refresh would otherwise fail).
  5. Resolve test model id, bind connections via item-level connections API
     (same workspace; fallback to global ADLS list for service-principal callers
     without Connection.Read.All)
  6. Refresh (Calculate by default; Full if any case opts in) via lib.refresh
     (TE2 XMLA -> REST API fallback)
  7. For each case: run DAX via AdomdClient (XMLA), assert against expected
  8. Print pass/fail summary
  9. ALWAYS DELETE test model in finally block

Test categories:
  - snapshot:   exact-string match against the value captured in the catalog
                file's __snapshots__/ sidecar. Use update_snapshots.py to
                (re)capture.
  - structural: column set / row count band / contains_any|all (for Search UDFs
                that depend on Direct Lake data; refresh_type: Full per case)
  - negative:   query MUST fail and error MUST match expected_error_regex

Snapshots live in a generated ``__snapshots__/<file>.yml`` sidecar next to each
catalog file (machine-owned; never hand-edited -- comments and case definitions
stay in the hand-authored .yml). The loader merges them back in by case id.

Run:
  python run_tests.py \
      --workspace-id <ws> \
      --source-model "Azure Data Insights" \
      --workspace-dir "workspace/HelixFabric-Insights/Azure Data Insights.SemanticModel" \
      --catalog-dir semantic_model_tests/_shared semantic_model_tests/azure_data_insights/unit

Add --update-snapshots to (re)capture expected results into the __snapshots__/
sidecars (prefer the update_snapshots.py wrapper, which also formats them).
Add --keep-model to skip teardown (debugging).
Add --filter SUBSTR to run a subset.

Exit code: 0 = all pass / snapshots updated. 1 = at least one failure. 2 = fatal.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
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
from fabric_cicd import FabricWorkspace, publish_all_items

# Add .deploy/workspace/ to sys.path so process_orchestrator + lib + operations
# all resolve. semantic_model_tests/run_tests.py -> parents[1] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEPLOY_WORKSPACE_DIR = _REPO_ROOT / ".deploy" / "workspace"
if str(_DEPLOY_WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_WORKSPACE_DIR))

from lib import connections, refresh, staging
from lib import fabric_api as fabric_api_lib
from lib.auth import (
    DEFAULT_FABRIC_API,
    FABRIC_SCOPE,
    PBI_SCOPE,
    Auth,
)
from process_orchestrator import (
    DeploymentAbortError,
    DeploymentContext,
    DeploymentPipeline,
    load_workspace_config,
)

# --- Constants ----------------------------------------------------------------

VALID_CATEGORIES = {"snapshot", "structural", "negative"}
VALID_REFRESH_TYPES = {"Calculate", "Full", "None"}

# Machine-owned snapshot sidecars live in this subdir next to each catalog file.
SNAPSHOT_DIR_NAME = "__snapshots__"
_SIDECAR_HEADER = (
    "# Generated snapshots -- do not edit by hand.\n"
    "# Recapture with:  python semantic_model_tests/update_snapshots.py --model <slug>\n"
    "# The hand-authored case definitions live in the sibling .yml file.\n"
)

ADOMD_NUGET_URL = (
    "https://www.nuget.org/api/v2/package/"
    "Microsoft.AnalysisServices.AdomdClient.retail.amd64"
)

# Pipeline config files (mirrors debug_deploy.py). DeploymentPipeline reads the
# preprocess steps from these YAML files so the test runner stays in sync with
# deploy_workspace.py automatically -- no parallel PRE_DEPLOY_SCRIPTS list.
_WORKSPACE_CONFIG = _DEPLOY_WORKSPACE_DIR / "configs" / "HelixFabric-Insights.yml"
_SHARED_CONFIG = _DEPLOY_WORKSPACE_DIR / "configs" / "shared.yml"



# --- Catalog ------------------------------------------------------------------


@dataclass
class TestCase:
    """
    A single AskADIA UDF test case loaded from a YAML catalog file.

    Holds the assertion contract (snapshot, structural, or negative) plus
    the DAX expression to execute. ``source_file`` is captured so the matching
    ``__snapshots__/`` sidecar can be located in ``--update-snapshots`` mode.
    """

    id: str
    category: str
    dax: str
    description: str = ""
    refresh_type: str | None = None
    expected_snapshot: str | None = None
    expected_columns: list[str] | None = None
    expected_row_count: dict | None = None
    contains_any: list[str] | None = None
    contains_all: list[str] | None = None
    expected_error_regex: str | None = None
    source_file: Path = field(default_factory=Path)


def load_catalog(catalog_dirs: list[Path]) -> list[TestCase]:
    """
    Load test cases from one or more catalog directories.

    Multiple directories let CI compose framework-wide tests (e.g.
    ``semantic_model_tests/_shared/``) with model-specific catalogs (e.g.
    ``semantic_model_tests/azure_data_insights/unit/`` and ``semantic_model_tests/azure_data_insights/smoke/``)
    in a single deployment.
    Case IDs must be globally unique across all supplied directories.
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
        sort_keys=False, default_flow_style=False, width=200, allow_unicode=True,
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
    cat = raw.get("category")
    if cat not in VALID_CATEGORIES:
        msg = f"{path}/{cid}: category must be one of {VALID_CATEGORIES}"
        raise ValueError(msg)
    if not raw.get("dax"):
        msg = f"{path}/{cid}: 'dax' is required"
        raise ValueError(msg)
    rt = raw.get("refresh_type")
    if rt is not None and rt not in VALID_REFRESH_TYPES:
        msg = f"{path}/{cid}: refresh_type must be {VALID_REFRESH_TYPES}"
        raise ValueError(msg)
    if cat == "negative" and not raw.get("expected_error_regex"):
        msg = f"{path}/{cid}: negative case requires 'expected_error_regex'"
        raise ValueError(msg)
    if "expected_snapshot" in raw or "expected_value" in raw:
        msg = (
            f"{path}/{cid}: inline 'expected_snapshot'/'expected_value' is not allowed; "
            f"snapshot values live in the __snapshots__/ sidecar (run update_snapshots.py)"
        )
        raise ValueError(msg)
    return TestCase(
        id=cid, category=cat, dax=raw["dax"],
        description=raw.get("description", ""), refresh_type=rt,
        expected_columns=raw.get("expected_columns"),
        expected_row_count=raw.get("expected_row_count"),
        contains_any=raw.get("contains_any"),
        contains_all=raw.get("contains_all"),
        expected_error_regex=raw.get("expected_error_regex"),
        source_file=path,
    )


def write_snapshot(case: TestCase, new_value: str) -> None:
    """Write case's captured value into its source file's snapshot sidecar."""
    snaps = load_snapshots(case.source_file)
    snaps[case.id] = new_value
    write_snapshots(case.source_file, snaps)


# --- Deploy / bind / refresh / execute / teardown -----------------------------


# --- AdomdClient out-of-proc helpers -----------------------------------------


def _ensure_adomd_client(target_dir: Path) -> Path:
    """Download AdomdClient DLL from NuGet if not already present."""
    import io
    import zipfile

    dll_path = target_dir / "Microsoft.AnalysisServices.AdomdClient.dll"
    if dll_path.exists():
        return dll_path

    print("      Downloading AdomdClient from NuGet...")
    resp = requests.get(ADOMD_NUGET_URL, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        member = "lib/net45/Microsoft.AnalysisServices.AdomdClient.dll"
        data = zf.read(member)
        dll_path.write_bytes(data)
    print(f"      AdomdClient downloaded ({dll_path.stat().st_size // 1024} KB)")
    return dll_path


def _find_csc() -> str:
    """Locate csc.exe from .NET Framework on Windows."""
    candidates = [
        Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    msg = "csc.exe not found; .NET Framework 4.x required on Windows agent"
    raise RuntimeError(msg)


def _compile_dax_runner(adomd_dll: Path, work_dir: Path) -> Path:
    """Compile DaxQueryRunner.cs into a standalone exe using csc.exe."""
    source = Path(__file__).resolve().parent / "DaxQueryRunner.cs"
    if not source.exists():
        msg = f"DaxQueryRunner.cs not found at {source}"
        raise FileNotFoundError(msg)

    exe_path = work_dir / "DaxQueryRunner.exe"
    csc = _find_csc()

    result = subprocess.run(
        [csc, "/nologo", "/target:exe",
         f"/reference:{adomd_dll}",
         f"/out:{exe_path}",
         str(source)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:800]
        msg = f"csc.exe compilation failed (exit {result.returncode}): {detail}"
        raise RuntimeError(msg)

    print(f"      Compiled DaxQueryRunner.exe ({exe_path.stat().st_size // 1024} KB)")
    return exe_path


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
    Execute all DAX cases via AdomdClient out-of-proc.

    Downloads AdomdClient from NuGet, compiles a standalone C# runner with
    csc.exe, and executes it against the XMLA endpoint. Avoids TE2 entirely
    for DAX queries (TE2 2.x only has scalar EvaluateDax, not full ExecuteDax).
    """
    work_dir = Path(tempfile.mkdtemp(prefix="udf-xmla-"))
    input_file = work_dir / "input.txt"
    output_file = work_dir / "output.jsonl"

    try:
        # Write sentinel-delimited input
        lines = []
        for c in cases:
            lines.append(f"===CASE {c.id}===")
            lines.append(c.dax.strip())
        input_file.write_text("\n".join(lines), encoding="utf-8")

        # Ensure AdomdClient DLL and compile the runner
        adomd_dll = _ensure_adomd_client(work_dir)
        runner_exe = _compile_dax_runner(adomd_dll, work_dir)

        # Resolve workspace display name for XMLA connection string
        headers = auth.headers(FABRIC_SCOPE)
        resp = requests.get(
            f"{fabric_api}/v1/workspaces/{workspace_id}",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        workspace_name = resp.json()["displayName"]

        # Build ADOMD connection string
        # User ID=; + Persist Security Info + Impersonation Level are required
        # for MSOLAP to recognise Password as a pre-acquired bearer token.
        pbi_token = auth.token(PBI_SCOPE)
        encoded_ws = urllib.parse.quote(workspace_name)
        data_source = f"powerbi://{xmla_endpoint}/v1.0/myorg/{encoded_ws}"
        conn_str = (
            f"Provider=MSOLAP;Data Source={data_source};"
            f"User ID=;Password={pbi_token};"
            f"Persist Security Info=True;Impersonation Level=Impersonate;"
            f"Initial Catalog={model_name}"
        )

        print(f"==> AdomdClient batch: {len(cases)} queries")

        env = os.environ.copy()
        env.update({
            "UDF_TEST_CONNSTR": conn_str,
            "UDF_TEST_INPUT": str(input_file),
            "UDF_TEST_OUTPUT": str(output_file),
        })

        result = subprocess.run(
            [str(runner_exe)],
            capture_output=True, text=True, check=False,
            env=env, cwd=str(work_dir),
        )

        if result.stdout:
            for line in result.stdout.strip().splitlines():
                print(f"    [ADOMD] {line}")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:500]
            print(f"    [ADOMD] exit {result.returncode}: {detail}")

        # Parse JSONL output
        results: dict[str, dict] = {}
        if output_file.exists():
            raw = output_file.read_text(encoding="utf-8")
            for line in raw.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    results[rec["id"]] = rec
                except (json.JSONDecodeError, KeyError) as exc:
                    print(f"    [WARN] bad JSONL line: {exc}")
        else:
            err_msg = f"Runner produced no output file (exit {result.returncode})"
            return {c.id: {"ok": False, "rows": [], "columns": [],
                            "error": {"message": err_msg}} for c in cases}

        # Fill missing cases
        for c in cases:
            if c.id not in results:
                results[c.id] = {"ok": False, "rows": [], "columns": [],
                                 "error": {"message": "case not in runner output"}}
        return results

    except Exception as exc:
        print(f"    [ADOMD] error: {exc}")
        return {c.id: {"ok": False, "rows": [], "columns": [],
                        "error": {"message": f"Runner failed: {exc}"}} for c in cases}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_cases_rest(
    cases: list[TestCase],
    *,
    dataset_id: str,
    workspace_id: str,
    auth: Auth,
) -> dict[str, dict]:
    """
    Execute DAX cases via Power BI Execute Queries REST API (local fallback).

    Runs one query at a time to keep error isolation per-case.
    """
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"
    results: dict[str, dict] = {}

    for c in cases:
        try:
            headers = auth.headers(PBI_SCOPE)
            body = {
                "queries": [{"query": c.dax.strip()}],
                "serializerSettings": {"includeNulls": True},
            }
            r = requests.post(url, headers=headers, json=body, timeout=120)
            if r.ok:
                resp = r.json()
                tables = resp.get("results", [{}])[0].get("tables", [])
                if tables:
                    rows = tables[0].get("rows", [])
                    columns = [col["name"] for col in tables[0].get("columns", [])] if tables[0].get("columns") else list(rows[0].keys()) if rows else []
                    results[c.id] = {"ok": True, "rows": rows, "columns": columns, "error": None}
                else:
                    results[c.id] = {"ok": True, "rows": [], "columns": [], "error": None}
            else:
                # Check for DAX execution error (expected for negative tests)
                err_body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                err_msg = _extract_pbi_error(err_body) or r.text[:500]
                results[c.id] = {"ok": False, "rows": [], "columns": [],
                                 "error": {"message": err_msg}}
        except Exception as exc:
            results[c.id] = {"ok": False, "rows": [], "columns": [],
                             "error": {"message": str(exc)}}

    return results


def _extract_pbi_error(body: dict) -> str | None:
    if not isinstance(body, dict):
        return None
    err = body.get("error", {})
    pbi = err.get("pbi.error", {}) or {}
    for d in pbi.get("details", []):
        if d.get("code") == "DetailsMessage":
            return (d.get("detail") or {}).get("value")
    return err.get("message") or pbi.get("code")


def delete_model(*, fabric_api, workspace_id, model_id, auth) -> bool:
    """Delete a SemanticModel by id. Returns True on 200/202/204."""
    url = f"{fabric_api}/v1/workspaces/{workspace_id}/semanticModels/{model_id}"
    r = connections.request_with_retry("DELETE", url, headers=auth.headers(FABRIC_SCOPE))
    return r.status_code in (200, 202, 204)


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


def _snapshot_value(result: dict) -> tuple[Any, str]:
    """
    Extract a comparable snapshot value from a DAX result.
    Returns (value, kind) where kind is 'scalar', 'table', or 'empty'.
    - 1 row, 1 col -> scalar (the cell value, including None for BLANK)
    - 1 row with AskADIA UDF shape {GeneratedDAX, AutoApplied, ...}
      -> scalar (the GeneratedDAX cell value); keeps snapshot stability when
      the askadia UDFs (AnswerQuestion / GenerateQuery) gain auxiliary
      columns. Snapshots target the generated DAX text, not the auxiliary
      auto-applied metadata.
    - multi-row or multi-col -> JSON-serialized table string
    - 0 rows -> empty string (valid snapshot for empty results)
    """
    if not result["ok"]:
        return None, "error"
    rows = result["rows"]
    cols = result["columns"]
    if not rows:
        return "", "empty"
    if len(cols) == 1 and len(rows) == 1:
        val = rows[0].get(cols[0])
        return val, "scalar"
    if len(rows) == 1:
        # Strip optional [..] wrapping that AdomdClient/DAX surfaces for ROW field names
        norm = {c.strip("[]"): c for c in cols}
        if "GeneratedDAX" in norm:
            val = rows[0].get(norm["GeneratedDAX"])
            return val, "scalar"
    # Table result -- JSON-serialize deterministically
    return json.dumps(rows, ensure_ascii=False, sort_keys=True), "table"


def _assert_snapshot(case: TestCase, result: dict) -> tuple[bool, str]:
    if not result["ok"]:
        return False, f"query failed: {result['error']['message']}"
    actual, kind = _snapshot_value(result)
    if kind == "error":
        return False, "query error (no result)"
    # Normalize: convert None to string "None" for comparison
    actual_str = str(actual) if actual is not None else "None"
    if case.expected_snapshot is not None:
        if actual_str == case.expected_snapshot:
            return True, "snapshot match"
        return False, _diff(case.expected_snapshot, actual_str)
    return False, "no snapshot captured (run update_snapshots.py)"


def _assert_structural(case: TestCase, result: dict) -> tuple[bool, str]:
    if not result["ok"]:
        return False, f"query failed: {result['error']['message']}"
    rows, cols = result["rows"], result["columns"]
    fail: list[str] = []
    # Column check: skip when 0 rows (XMLA may not return column metadata for empty results)
    if case.expected_columns and rows:
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
    if case.contains_any or case.contains_all:
        flat = "\n".join(str(v) for r in rows for v in r.values() if v is not None)
        if case.contains_any and not any(n in flat for n in case.contains_any):
            fail.append(f"contains_any {case.contains_any} matched none")
        if case.contains_all:
            for needle in case.contains_all:
                if needle not in flat:
                    fail.append(f"contains_all missing {needle!r}")
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
    diff = list(difflib.unified_diff(
        expected.splitlines(keepends=True), actual.splitlines(keepends=True),
        fromfile="expected", tofile="actual", n=2,
    ))
    if len(diff) > max_lines:
        diff = diff[:max_lines] + [f"... ({len(diff) - max_lines} more lines)\n"]
    return "snapshot mismatch:\n" + "".join(diff)


# --- CLI / orchestration ------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI args. See module docstring + --help for the contract."""
    p = argparse.ArgumentParser(description="AskADIA semantic-model test runner")
    p.add_argument("--workspace-id", required=True)
    p.add_argument("--source-model", required=True,
                   help="DisplayName of the production model to test (e.g. 'Azure Data Insights')")
    p.add_argument("--workspace-dir", required=True, type=Path,
                   help="Path to the source *.SemanticModel directory in the repo")
    p.add_argument("--workspace-dir-name",
                   help="Workspace folder name under workspace/ (e.g. 'HelixFabric-Insights'). "
                        "Used to look up env-mapped connection IDs in env_connection_ids.json. "
                        "Defaults to the parent directory name of --workspace-dir.")
    p.add_argument("--catalog-dir", required=True, type=Path, nargs="+",
                   help="One or more catalog directories. Cases from all dirs are merged; case IDs must be globally unique.")
    p.add_argument("--environment", default="dev", choices=["dev", "test", "prod"],
                   help="Drives parameter.yml find/replace (env-correct storage GUIDs in staged TMDL) "
                        "AND which env's connection IDs are bound (from env_connection_ids.json). "
                        "Defaults to 'dev'. CI passes target-branch-derived value.")
    p.add_argument("--api-root", default=DEFAULT_FABRIC_API)
    p.add_argument("--xmla-endpoint", default="api.powerbi.com",
                   help="XMLA endpoint hostname (default: api.powerbi.com)")
    p.add_argument("--refresh-type", default="Calculate", choices=["Calculate", "Full", "None"])
    p.add_argument("--update-snapshots", action="store_true",
                   help="Capture current results into the YAML catalog instead of asserting")
    p.add_argument("--keep-model", action="store_true", help="Skip teardown (debugging)")
    p.add_argument("--interactive-auth", action="store_true",
                   help="Use InteractiveBrowserCredential instead of AzureCliCredential")
    p.add_argument("--filter", help="Only run cases whose id contains this substring")
    return p.parse_args()


def main() -> int:
    """Run the full test pipeline. Returns 0=pass, 1=test failures, 2=fatal."""
    args = parse_args()
    cases = load_catalog(args.catalog_dir)
    if args.filter:
        cases = [c for c in cases if args.filter in c.id]
    if args.update_snapshots:
        cases = [c for c in cases if c.category == "snapshot"]
    if not cases:
        print(f"No cases matched (catalog={args.catalog_dir}, filter={args.filter!r})", file=sys.stderr)
        return 2

    # Fail fast on missing snapshots BEFORE the expensive deploy/refresh. Without
    # this a snapshot case with no captured value would deploy, refresh, run DAX,
    # then fail late with "no snapshot captured".
    if not args.update_snapshots:
        missing = [c.id for c in cases if c.category == "snapshot" and c.expected_snapshot is None]
        if missing:
            print(
                f"==> {len(missing)} snapshot case(s) have no captured value; run "
                f"update_snapshots.py to (re)capture: {', '.join(missing)}",
                file=sys.stderr,
            )
            return 2

    skipped_full = [c for c in cases if c.refresh_type == "Full" and args.refresh_type != "Full"]
    if skipped_full:
        ids = ", ".join(c.id for c in skipped_full[:5]) + ("..." if len(skipped_full) > 5 else "")
        print(f"==> Note: {len(skipped_full)} case(s) want refresh_type=Full but we're running "
              f"{args.refresh_type}; they will run against the Calculate-refreshed model. "
              f"Pass --refresh-type Full to validate them. ({ids})")
    base_refresh = args.refresh_type

    auth = Auth(interactive=args.interactive_auth)
    auth.warm()
    fabric_api = args.api_root.rstrip("/")
    env = args.environment
    workspace_dir_name = args.workspace_dir_name or args.workspace_dir.parent.name
    test_model_name = staging.make_test_model_name("DEBUG_UnitTest", env, args.source_model)
    print(f"==> Test model:    {test_model_name}")
    print(f"==> Workspace:     {args.workspace_id}")
    print(f"==> Environment:   {env}  (drives parameter.yml + connection bind)")
    print(f"==> Cases:         {len(cases)} loaded from {len(args.catalog_dir)} dir(s): {', '.join(str(d) for d in args.catalog_dir)}")
    print(f"==> Refresh:       {base_refresh}")

    test_id: str | None = None
    temp_repo: Path | None = None
    results: list[tuple[TestCase, bool, str, float]] = []
    fatal: Exception | None = None

    try:
        # 1. Stage source TMDL into temp repo. strip_rls=True because the
        # publishing identity (SP in CI; user in local) usually isn't listed
        # in RLS role member sets, and tests don't need RLS coverage at this
        # layer (RLS evaluation is covered by separate query-time tests).
        print(f"==> Staging source from {args.workspace_dir}")
        temp_repo = Path(tempfile.mkdtemp(prefix="udf-test-"))
        staging.stage_model(
            source_dir=args.workspace_dir,
            model_name=test_model_name,
            output_dir=temp_repo,
            strip_rls=True,
        )

        # 2. Copy parameter.yml so FabricWorkspace's find/replace fires for env.
        # Without this fabric_cicd silently keeps source TMDL paths (which are
        # the dev baseline), and binding env-mapped connections fails with
        # BindConnectionDetailNotFound when env != dev.
        source_parameter_yml = args.workspace_dir.parent / "parameter.yml"
        if source_parameter_yml.exists():
            shutil.copy2(source_parameter_yml, temp_repo / "parameter.yml")

        # 3. Load + merge YAML config; inject source_model_name so the
        # bundled `setup_askadia_framework` op resolves the real overlay slug
        # from the source model name (not the throwaway test name) and clear
        # post_process so YAML's auto-refresh doesn't fire before our explicit
        # bind_connections + refresh sequence (the staged DirectLake model has
        # no bound connections at publish time).
        shared_cfg = load_workspace_config(_SHARED_CONFIG) or {}
        ws_cfg = load_workspace_config(_WORKSPACE_CONFIG) or {}
        config = {**shared_cfg, **ws_cfg}
        staging.patch_workspace_config_for_staged_model(
            config,
            source_model_name=args.source_model,
        )

        # 4. Run the FULL prod preprocess+publish chain via DeploymentPipeline.
        # Same chain as deploy_workspace.py + debug_deploy.py: validate_item,
        # merge_shared_scaffold, generate_copilot_questions, all CSX metadata
        # generators, generate_copilot_schema. unpublish is a no-op: orphan
        # cleanup against the test workspace would wipe the source model and
        # every other unmanaged item. The `finally` block deletes the test
        # model on its own. fabric_api_root scopes the fabric_cicd
        # DEFAULT_API_ROOT_URL mutation to the publish call. environment=env
        # drives parameter.yml find/replace -- staged TMDL gets the env's
        # storage GUIDs substituted in (so a test on Main PR sees prod paths).
        ctx = DeploymentContext(
            workspace_id=args.workspace_id,
            workspace_directory_name=args.workspace_dir.parent.name,
            environment=env,
            release_type="default",
            item_type_in_scope=["SemanticModel"],
            token_credential=auth.cred,
            fabric_api_url=fabric_api,
            xmla_endpoint=args.xmla_endpoint,
            repository_directory=str(temp_repo),
        )
        pipeline = DeploymentPipeline(ctx, config)
        try:
            with fabric_api_lib.fabric_api_root(fabric_api):
                pipeline.run(
                    create_workspace=lambda: FabricWorkspace(
                        workspace_id=args.workspace_id,
                        environment=env,
                        repository_directory=str(temp_repo),
                        item_type_in_scope=["SemanticModel"],
                        token_credential=auth.cred,
                    ),
                    publish=lambda ws, ex: publish_all_items(ws, item_name_exclude_regex=ex),
                    unpublish=lambda ws: None,  # noqa: ARG005
                )
        except DeploymentAbortError as e:
            msg = f"Pipeline aborted: {e}"
            raise RuntimeError(msg) from e

        # 5. Resolve test model id (needed for bind + refresh REST fallback).
        test_id = connections.resolve_item_id(
            fabric_api=fabric_api,
            workspace_id=args.workspace_id,
            display_name=test_model_name,
            item_type="SemanticModel",
            auth=auth,
        )
        if not test_id:
            msg = f"Test model {test_model_name} not found after deploy"
            raise RuntimeError(msg)
        print(f"==> Test model id: {test_id}")

        # 6. Bind explicit env-mapped connection IDs from
        # .deploy/workspace/configs/env_connection_ids.json. The test SP
        # has 'Use' permission on every env's connection objects (no
        # cross-workspace read needed). Strict by design: any failure here
        # raises -- silent skips would mask bind regressions and produce
        # opaque "model returned no data" downstream failures.
        connection_ids = connections.load_env_connection_ids(
            repo_root=_REPO_ROOT,
            workspace_dir_name=workspace_dir_name,
            source_model=args.source_model,
            env=env,
        )
        n = connections.bind_explicit_connections(
            fabric_api=fabric_api,
            target_workspace_id=args.workspace_id,
            target_model_id=test_id,
            connection_ids=connection_ids,
            auth=auth,
        )
        print(f"==> Bound {n} connection(s) to test model ({env})")

        # 7. Refresh via REST API. Preview TMDL properties are injected after
        # TE2 preprocessing and may not be loadable by the current TE2.
        if base_refresh != "None":
            print(f"==> Triggering {base_refresh} refresh")
            t0 = time.time()
            refresh.refresh_model(
                model_name=test_model_name,
                workspace_id=args.workspace_id,
                fabric_api=fabric_api,
                xmla_endpoint=args.xmla_endpoint,
                auth=auth,
                refresh_type=base_refresh,
                dataset_id=test_id,
                rest_only=True,
            )
            print(f"==> Refresh complete in {time.time() - t0:.1f}s")

        # Choose DAX execution backend:
        #   interactive (local) → REST API (no XMLA auth issues)
        #   pipeline (SP)       → AdomdClient via XMLA (fast, batched)
        if args.interactive_auth:
            dax_backend = "REST API"
            def _run_dax(c):
                return run_cases_rest(c, dataset_id=test_id,
                                      workspace_id=args.workspace_id, auth=auth)
        else:
            dax_backend = "AdomdClient"
            xmla_kw = dict(model_name=test_model_name, fabric_api=fabric_api,
                           workspace_id=args.workspace_id,
                           xmla_endpoint=args.xmla_endpoint, auth=auth)
            def _run_dax(c):
                return run_cases_xmla(c, **xmla_kw)

        if args.update_snapshots:
            print(f"==> Running {len(cases)} snapshot cases via {dax_backend}")
            t0 = time.time()
            dax_results = _run_dax(cases)
            print(f"==> All queries complete in {time.time() - t0:.1f}s")
            for case in cases:
                ct0 = time.time()
                result = dax_results.get(case.id, {"ok": False, "rows": [], "columns": [],
                                                    "error": {"message": "no result"}})
                try:
                    val, kind = _snapshot_value(result)
                    if result["ok"] and kind != "error":
                        snap_str = str(val) if val is not None else "None"
                        write_snapshot(case, snap_str)
                        passed, msg = True, f"snapshot updated ({kind}, {len(snap_str)} chars)"
                    else:
                        err = result["error"]["message"] if not result["ok"] else "no result"
                        passed, msg = False, f"could not capture snapshot: {err}"
                except Exception as exc:
                    passed, msg = False, f"runner exception: {exc}"
                results.append((case, passed, msg, time.time() - ct0))
        else:
            print(f"==> Running {len(cases)} cases via {dax_backend}")
            t0 = time.time()
            dax_results = _run_dax(cases)
            print(f"==> All queries complete in {time.time() - t0:.1f}s")
            for case in cases:
                result = dax_results.get(case.id, {"ok": False, "rows": [], "columns": [],
                                                    "error": {"message": "no result from runner"}})
                try:
                    passed, msg = assert_case(case, result)
                except Exception as exc:
                    passed, msg = False, f"runner exception: {exc}"
                results.append((case, passed, msg, 0.0))
    except Exception as exc:
        fatal = exc
        traceback.print_exc()
    finally:
        if temp_repo and temp_repo.exists():
            shutil.rmtree(temp_repo, ignore_errors=True)
        if test_id and not args.keep_model:
            try:
                ok = delete_model(fabric_api=fabric_api, workspace_id=args.workspace_id,
                                  model_id=test_id, auth=auth)
                print(f"==> Teardown DELETE: {'ok' if ok else 'FAILED -- manual cleanup needed'}")
            except Exception as exc:
                print(f"==> Teardown error: {exc}")
        elif args.keep_model and test_id:
            print(f"==> --keep-model: leaving {test_model_name} ({test_id}) deployed")

    if fatal:
        return 2

    _print_summary(results)
    if args.update_snapshots:
        print(
            "==> NOTE: snapshot sidecars were written in PyYAML format. Run "
            '`npx prettier --write "semantic_model_tests/**/__snapshots__/*.yml"` '
            "before committing (the update_snapshots.py wrapper does this for you).",
        )
    fails = sum(1 for _, p, _, _ in results if not p)
    return 1 if fails else 0


def _print_summary(results: Iterable[tuple[TestCase, bool, str, float]]) -> None:
    results = list(results)
    passed = sum(1 for _, p, _, _ in results if p)
    failed = len(results) - passed
    print()
    print("=" * 80)
    print(f"  {len(results)} run, {passed} passed, {failed} failed")
    print("=" * 80)
    for case, ok, msg, dur in results:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {case.category:11s} {case.id:40s} ({dur:.2f}s)")
        if not ok:
            for line in msg.splitlines() or [msg]:
                print(f"           {line}")


if __name__ == "__main__":
    sys.exit(main())
