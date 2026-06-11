"""Abstract token grammar for the model emitter.

Bodies in the canonical content store never hard-code environment-specific
values.  Instead they use abstract tokens the emitter resolves at emit time:

  ``{{model-guid:<slug>}}``
      The Power BI artifact (dataset) GUID for a model, resolved to the target
      environment's dataset GUID at emit time.

  ``{{ref:<anchor>}}``
      A cross-reference resolving to the referenced row's backtick'd ``key`` (its
      anchor — the stable handle the LLM fetches rows by), used for intra-model
      "see the X row" phrasing.

The token engine here is intentionally tiny: ``detokenize`` replaces every token
and fails loud on the first one it cannot resolve (never a silent passthrough).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A token is ``{{<kind>:<arg>}}`` where arg may contain ``-``, ``_``, ``.`` and
# lowercase alnum.  Kept deliberately strict so a stray ``{{`` in prose never
# accidentally parses as a token.
_TOKEN_RE = re.compile(
    r"\{\{(?P<kind>model-guid|ref):(?P<arg>[A-Za-z0-9_./-]+)\}\}"
)


@dataclass(frozen=True)
class Token:
    kind: str
    arg: str
    raw: str


def find_tokens(text: str) -> list[Token]:
    return [
        Token(kind=m.group("kind"), arg=m.group("arg"), raw=m.group(0))
        for m in _TOKEN_RE.finditer(text)
    ]


@dataclass
class TokenMap:
    """Resolution table for a single emit target.

    ``guids`` maps model slug -> artifact/dataset GUID.
    ``refs``  maps anchor -> the replacement string (the row's backtick'd key).
    """

    guids: dict[str, str] = field(default_factory=dict)
    refs: dict[str, str] = field(default_factory=dict)

    def resolve(self, token: Token) -> str:
        if token.kind == "model-guid":
            if token.arg not in self.guids:
                raise KeyError(f"Unresolved model-guid token: {token.raw}")
            return self.guids[token.arg]
        if token.kind == "ref":
            if token.arg not in self.refs:
                raise KeyError(f"Unresolved ref token: {token.raw}")
            return str(self.refs[token.arg])
        raise KeyError(f"Unknown token kind: {token.raw}")


def detokenize(text: str, token_map: TokenMap) -> str:
    """Replace every token in ``text`` using ``token_map``.

    Raises ``KeyError`` if any token cannot be resolved, which the validator and
    emitters surface as a hard failure (never a silent passthrough).
    """

    def _sub(m: re.Match) -> str:
        tok = Token(kind=m.group("kind"), arg=m.group("arg"), raw=m.group(0))
        return token_map.resolve(tok)

    return _TOKEN_RE.sub(_sub, text)


# --- Leftover-token / directive guards ----------------------------------------
# Regression guard: the store renders to the model target only (there is no
# ``{{only}}`` conditional grammar). If skill-format ``{{only}}`` markers ever
# leak into a body, the emitter fails loudly instead of shipping the markers.
# The open branch is colon-agnostic (``{{only:x}}`` and ``{{only x}}`` both
# match) so it stays symmetric with the colon-less close ``{{/only}}`` -- a
# stray open marker must never pass silently.

_ONLY_RESIDUE_RE = re.compile(r"\{\{only\b[^}]*\}\}|\{\{/only\}\}")


def find_unresolved_directives(text: str) -> list[str]:
    """Return any leftover ``{{only}}`` / ``{{/only}}`` residue.

    Canonical bodies must contain none; a non-empty result means skill-format
    conditional markers leaked into the single-source store."""
    return _ONLY_RESIDUE_RE.findall(text)


# A ``{{kind:arg}}`` fragment surviving a full detokenize pass means a MALFORMED
# token slipped past the strict grammar -- e.g. ``{{ref:bad anchor}}`` (space in
# the arg) or a typo'd kind ``{{reff:workflow}}``. ``detokenize`` only fails loud
# on WELL-FORMED tokens it cannot resolve; this closes the gap so a typo can never
# silently ship literal ``{{...}}`` into deployed model instructions.
#
# Scoped to brace pairs containing a colon -- that is what distinguishes our
# ``kind:arg`` tokens from the legitimate ``{{UPPER_SNAKE}}`` report-template
# placeholders the 360 one-shot rows hand to the LLM (those carry no inner colon).
# Only used on FULLY resolved output (the model emitter) -- NOT the router, which
# intentionally leaves ``{{model-guid:...}}`` for the consumer's per-env resolution.
_RESIDUAL_BRACE_RE = re.compile(r"\{\{[^{}\n]*:[^{}\n]*\}\}")


def find_residual_tokens(text: str) -> list[str]:
    """Return any leftover ``{{kind:arg}}``-shaped fragments after detokenization."""
    return _RESIDUAL_BRACE_RE.findall(text)

