"""Canonical ADIA instruction source — core library.

Single source of truth for ADIA copilot instruction content that is emitted to
two targets:

  1. a consumer plugin/skill (markdown), and
  2. the HelixData semantic models' ``_COPILOT_INSTRUCTIONS`` table + thin
     ``Copilot/Instructions/instructions.md`` router (TMDL / markdown).

The canonical store keeps content body text once and resolves abstract tokens
differently per emitter.  See ``tokens.py`` for the token grammar and
``README.md`` for the authoring model.
"""

from .tokens import TokenMap, detokenize, find_tokens  # noqa: F401
