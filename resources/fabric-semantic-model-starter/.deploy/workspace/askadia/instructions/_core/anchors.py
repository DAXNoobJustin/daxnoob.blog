"""Markdown intra-document anchor validation.

Each row's ``Instructions`` is fetched and read on its own, so every in-page
anchor link ``](#slug)`` in a row must target a heading WITHIN that same row.
A link to a heading that lives in another row -- e.g. ``[Workflow](#workflow)``
from the ``udf-reference`` row, whose heading is in the ``workflow`` row --
dead-links at runtime. Cross-row pointers must instead use a ``{{ref:<anchor>}}``
token, which renders to the target row's fetch key. ``find_dangling_anchors``
lets the emitter fail loud on any such dangling anchor (the static class the
token guards in ``tokens.py`` do not cover, since a raw Markdown anchor is not
a token).
"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(?P<text>.+?)[ \t]*#*$", re.MULTILINE)
_ANCHOR_LINK_RE = re.compile(r"\]\(#(?P<slug>[^)]+)\)")
_FENCE_RE = re.compile(r"^\s*(?:`{3,}|~{3,})")


def _strip_code_fences(text: str) -> str:
    """Drop fenced code blocks so anchors/headings inside a code example are not
    mistaken for real links or headings."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def heading_slug(text: str) -> str:
    """GitHub-style heading slug: lowercase, drop backticks, strip punctuation
    other than word chars / spaces / hyphens, then spaces -> hyphens."""
    s = text.strip().lower().replace("`", "")
    s = re.sub(r"[^\w\s-]", "", s)
    return s.replace(" ", "-")


def find_dangling_anchors(text: str) -> list[str]:
    """Return the ``#slug`` targets that link to no heading within ``text``."""
    body = _strip_code_fences(text)
    headings = {heading_slug(m.group("text")) for m in _HEADING_RE.finditer(body)}
    return [
        f"#{m.group('slug')}"
        for m in _ANCHOR_LINK_RE.finditer(body)
        if m.group("slug") not in headings
    ]
