"""
Programmatic detection of the upstream long-lived branch.

Algorithm:
  1. For each candidate in (Main, Test, Develop):
        merge_base = git merge-base HEAD origin/<candidate>
        distance   = git rev-list --count merge_base..HEAD
  2. Pick the candidate with the smallest distance.
  3. Tie-break order is the iteration order itself: Main first, then Test,
     then Develop -- so the most-conservative branch wins on ties.

Why it works: every commit shares the same merge-base with its actual
upstream, so the upstream's count is always <= the others'. Ties are rare
in practice (only zero-commit feature branches), and defaulting to Main
on a tie is harmless because no behavior change has happened yet.

Independent of branch naming convention -- no reliance on _OnTest / _OnMain
suffixes. Detached HEAD or no remote -> default Develop with a warning.
"""

from __future__ import annotations

import subprocess
import sys

# Iteration order = tie-break preference: Main > Test > Develop.
_LONG_LIVED_BRANCHES = ("Main", "Test", "Develop")

# Branch -> environment slug used by parameter.yml find/replace + workspace IDs.
_ENV_BY_BRANCH = {
    "Develop": "dev",
    "Test": "test",
    "Main": "prod",
}


def _git(*args: str) -> tuple[int, str]:
    """Run a git command; return (returncode, stripped stdout)."""
    try:
        proc = subprocess.run(
            ("git", *args),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, ""
    return proc.returncode, proc.stdout.strip()


def _fetch_long_lived_branches() -> None:
    """
    Best-effort fetch so merge-base distances reflect the latest origin tip.

    Failure is non-fatal: if origin is unreachable, we fall through to whatever
    the local refs already point at.
    """
    _git("fetch", "origin", *_LONG_LIVED_BRANCHES, "--quiet")


def get_upstream_branch(*, fetch: bool = False) -> str:
    """
    Return the long-lived branch this HEAD descends from.

    Returns one of "Develop", "Test", "Main". Defaults to "Develop" with a
    warning when detection fails (no remote refs, detached HEAD with no
    merge-base, etc).

    Args:
        fetch: If True, run ``git fetch origin Develop Test Main`` before
            computing distances so local refs reflect the latest origin tips.
            Defaults to False -- the 1-2s VPN-bound fetch tax is rarely worth
            paying. Local devs typically know which branch they're on; CI
            does a fresh checkout. Pass True from a long-running session that
            needs to detect a recent retarget.

    """
    if fetch:
        _fetch_long_lived_branches()

    best: str | None = None
    best_distance = sys.maxsize
    for candidate in _LONG_LIVED_BRANCHES:
        rc, base = _git("merge-base", "HEAD", f"origin/{candidate}")
        if rc != 0 or not base:
            continue
        rc, count = _git("rev-list", "--count", f"{base}..HEAD")
        if rc != 0 or not count:
            continue
        try:
            distance = int(count)
        except ValueError:
            continue
        if distance < best_distance:
            best = candidate
            best_distance = distance

    if best is None:
        print(
            "==> WARNING: could not resolve upstream branch from origin refs; "
            "defaulting to 'Develop'",
            file=sys.stderr,
        )
        return "Develop"
    return best


def resolve_environment(branch: str) -> str:
    """Map a long-lived branch name to its environment slug (dev/test/prod)."""
    try:
        return _ENV_BY_BRANCH[branch]
    except KeyError as exc:
        msg = (
            f"Unknown long-lived branch '{branch}'; expected one of "
            f"{sorted(_ENV_BY_BRANCH)}"
        )
        raise ValueError(
            msg
        ) from exc
