#!/usr/bin/env python3
"""Rebrand the framework namespace (default: "AskADIA") to a name of your choice.

This package is published with the canonical brand **AskADIA** baked in verbatim,
so the upstream repo emits byte-for-byte identical output and never has to run
this tool. It exists purely for *adopters* who fork/vendor the ``askadia/``
package and want it to carry their own brand instead.

What it does
------------
1. Case-aware string replacement of the brand across every text file in the
   package, in all three forms it appears in:

       AskADIA   (Pascal)   -> --pascal   e.g. "DataChat"   | brand text + the
                                                              ``Local.AskADIA.*``
                                                              DAX UDF namespace
       ASKADIA   (upper)    -> --upper    e.g. "DATACHAT"   | constants + env vars
                                                              (ASKADIA_ROOT,
                                                              ASKADIA_CONFIG_JSON)
       askadia   (lower)    -> --lower    e.g. "datachat"   | dir/package, op
                                                              names, config keys,
                                                              path strings

2. Renames the two brand-named files (``git mv`` when in a repo, else a plain
   move) and updates every in-package reference to them:

       udf/common/askadia_config.json      -> <lower>_config.json
       deploy/setup_askadia_framework.py    -> setup_<lower>_framework.py

3. Optionally renames the package directory itself (``askadia/`` -> ``<lower>/``).

4. Re-blesses the golden artifacts (``emit_model.py --update-golden`` per model +
   ``emit_router.py --update-golden``) and runs ``test_roundtrip.py`` so you get
   a clean, self-consistent, test-passing package on the other side.

Usage
-----
    python rename_namespace.py --pascal DataChat --lower datachat
    python rename_namespace.py --pascal DataChat --lower datachat --keep-dir-name
    python rename_namespace.py --check        # CI guard: assert canonical brand intact

Important caveats (see RENAMING.md)
-----------------------------------
* The ``Local.<Pascal>.*`` UDF names are a RUNTIME CONTRACT with the consuming
  skill/agent. If you rename them here you MUST rename them on the consumer side
  too, or queries will fail.
* This tool only rewrites files INSIDE the package. Host wiring that lives
  outside ``askadia/`` (e.g. an orchestrator that does
  ``from setup_askadia_framework import ...`` or a deploy config that names the
  ``setup_askadia_framework`` op) must be updated by hand — RENAMING.md lists
  exactly what to touch.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Canonical brand forms shipped upstream. Replacement is case-sensitive and the
# three forms are disjoint by case, so order does not matter.
CANON_PASCAL = "AskADIA"
CANON_UPPER = "ASKADIA"
CANON_LOWER = "askadia"

TEXT_EXTS = {
    ".py", ".md", ".json", ".yml", ".yaml", ".csx", ".tmdl",
    ".txt", ".cfg", ".ini", ".toml",
}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".mypy_cache"}
# Never rewrite the tool or its doc — they intentionally quote the canonical brand.
SELF_SKIP = {"rename_namespace.py", "RENAMING.md"}

# Brand-named files and their rename templates ({lower} -> new lower form).
FILE_RENAMES = (
    (Path("udf/common/askadia_config.json"), "udf/common/{lower}_config.json"),
    (Path("deploy/setup_askadia_framework.py"), "deploy/setup_{lower}_framework.py"),
)


def _git_toplevel(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _move(src: Path, dst: Path, toplevel: Path | None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if toplevel is not None:
        subprocess.run(
            ["git", "-C", str(toplevel), "mv", str(src), str(dst)],
            check=True,
        )
    else:
        src.rename(dst)


def iter_text_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SELF_SKIP:
            continue
        if p.suffix.lower() in TEXT_EXTS:
            yield p


def replace_in_text(root: Path, pascal: str, upper: str, lower: str) -> int:
    changed = 0
    for p in iter_text_files(root):
        try:
            # newline="" preserves the file's existing line endings (repo is LF).
            original = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = (
            original.replace(CANON_PASCAL, pascal)
            .replace(CANON_UPPER, upper)
            .replace(CANON_LOWER, lower)
        )
        if updated != original:
            p.write_text(updated, encoding="utf-8", newline="")
            changed += 1
    return changed


def rename_files(root: Path, lower: str, toplevel: Path | None) -> list[str]:
    done = []
    for rel, template in FILE_RENAMES:
        src = root / rel
        if not src.exists():
            continue
        dst = root / template.format(lower=lower)
        if src.resolve() == dst.resolve():
            continue
        _move(src, dst, toplevel)
        done.append(f"{rel}  ->  {dst.relative_to(root)}")
    return done


def rename_package_dir(root: Path, lower: str, toplevel: Path | None) -> Path:
    if root.name != CANON_LOWER:
        return root
    dst = root.with_name(lower)
    _move(root, dst, toplevel)
    return dst


def run_step(label: str, args: list[str], cwd: Path) -> bool:
    print(f"  [{label}] {' '.join(args)}")
    proc = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-2000:])
        sys.stderr.write(proc.stderr[-2000:])
        print(f"  [{label}] FAILED (exit {proc.returncode})")
        return False
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    print(f"  [{label}] ok  {tail}")
    return True


def rebless_and_test(instructions_dir: Path) -> bool:
    models_dir = instructions_dir / "models"
    slugs = sorted(d.name for d in models_dir.iterdir() if (d / "model.json").exists())
    ok = True
    for slug in slugs:
        ok &= run_step(
            "emit-model",
            [sys.executable, "emit_model.py", "--slug", slug, "--update-golden"],
            instructions_dir,
        )
    ok &= run_step(
        "emit-router",
        [sys.executable, "emit_router.py", "--update-golden"],
        instructions_dir,
    )
    ok &= run_step(
        "roundtrip-tests",
        [sys.executable, "test_roundtrip.py"],
        instructions_dir,
    )
    return ok


def residual_brand(root: Path) -> list[Path]:
    hits = []
    for p in iter_text_files(root):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if CANON_PASCAL in text or CANON_UPPER in text or CANON_LOWER in text:
            hits.append(p)
    return hits


def cmd_check(root: Path) -> int:
    """CI guard: assert the package still carries the canonical brand (no drift)."""
    canonical_present = any(
        CANON_PASCAL in p.read_text(encoding="utf-8", errors="ignore")
        for p in iter_text_files(root)
    )
    if not canonical_present:
        print("CHECK FAILED: canonical brand 'AskADIA' not found — namespace drifted.")
        return 1
    print("CHECK ok: canonical 'AskADIA' brand intact.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pascal", help='New Pascal-case brand, e.g. "DataChat".')
    ap.add_argument("--lower", help='New lower-case token, e.g. "datachat".')
    ap.add_argument("--upper", help="New upper-case token. Defaults to --lower uppercased.")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent,
                    help="Package root to rewrite (defaults to this script's directory).")
    ap.add_argument("--keep-dir-name", action="store_true",
                    help="Do not rename the package directory itself.")
    ap.add_argument("--keep-filenames", action="store_true",
                    help="Do not rename brand-named files inside the package.")
    ap.add_argument("--no-rebless", action="store_true",
                    help="Skip golden re-bless + roundtrip tests.")
    ap.add_argument("--check", action="store_true",
                    help="CI guard: verify the canonical 'AskADIA' brand is intact, then exit.")
    args = ap.parse_args()

    root = args.root.resolve()

    if args.check:
        return cmd_check(root)

    if not args.pascal or not args.lower:
        ap.error("--pascal and --lower are required (unless --check).")
    upper = args.upper or args.lower.upper()

    if CANON_PASCAL in (args.pascal,) and CANON_LOWER in (args.lower,):
        print("New brand equals the canonical brand — nothing to do.")
        return 0

    toplevel = _git_toplevel(root)
    mode = "git" if toplevel else "filesystem"
    print(f"Rebranding AskADIA/ASKADIA/askadia -> {args.pascal}/{upper}/{args.lower}")
    print(f"  root: {root}")
    print(f"  rename mode: {mode}")

    n = replace_in_text(root, args.pascal, upper, args.lower)
    print(f"  rewrote {n} file(s)")

    if not args.keep_filenames:
        for line in rename_files(root, args.lower, toplevel):
            print(f"  renamed file  {line}")

    eff_root = root
    if not args.keep_dir_name:
        eff_root = rename_package_dir(root, args.lower, toplevel)
        if eff_root != root:
            print(f"  renamed dir   {root.name}  ->  {eff_root.name}")

    leftovers = residual_brand(eff_root)
    if leftovers:
        print(f"  WARNING: canonical brand still present in {len(leftovers)} file(s):")
        for p in leftovers[:20]:
            print(f"    {p.relative_to(eff_root)}")

    if not args.no_rebless:
        print("Re-blessing goldens and running roundtrip tests...")
        if not rebless_and_test(eff_root / "instructions"):
            print("Re-bless/tests FAILED — review output above.")
            return 1

    print("Done. Review `git status` / `git diff` before committing.")
    print("Reminder: update host wiring outside the package (see RENAMING.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
