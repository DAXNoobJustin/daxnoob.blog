"""Canonical filesystem anchors for the self-contained AskADIA framework package.

Every deploy op in this package resolves framework paths from here, so the whole
``askadia/`` tree can be relocated (or handed to another team) without
editing path math in a dozen modules. ``ASKADIA_ROOT`` is the package root; an
adopting team only needs the host to put this ``deploy/`` directory on
``sys.path`` and register the single ``setup_askadia_framework`` operation.

Layout owned here::

    askadia/                      ASKADIA_ROOT
        config/model_guids.yml           MODEL_GUIDS_YML   (per-env dataset GUIDs)
        udf/common/                      UDF_COMMON_DIR    (canonical UDFs + tables + config)
        udf/models/<slug>/               OVERLAY_MODELS_DIR (per-model overlay)
        instructions/                    INSTRUCTIONS_DIR  (instruction store + emitters)
        deploy/                          DEPLOY_DIR        (this package: ops)
        deploy/tabular_scripts/          TABULAR_SCRIPTS_DIR (framework csx)
"""

from __future__ import annotations

from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
ASKADIA_ROOT = DEPLOY_DIR.parent

UDF_DIR = ASKADIA_ROOT / "udf"
UDF_COMMON_DIR = UDF_DIR / "common"
UDF_COMMON_TABLES_DIR = UDF_COMMON_DIR / "tables"
OVERLAY_MODELS_DIR = UDF_DIR / "models"
ASKADIA_CONFIG_JSON = UDF_COMMON_DIR / "askadia_config.json"
CANONICAL_FUNCTIONS_TMDL = UDF_COMMON_DIR / "functions.tmdl"

INSTRUCTIONS_DIR = ASKADIA_ROOT / "instructions"
INSTRUCTION_MODELS_DIR = INSTRUCTIONS_DIR / "models"


def instruction_model_json(slug: str) -> Path:
    """The per-model instruction registry (``instructions/models/<slug>/model.json``).

    Mirrors ``_core.paths.model_json_path`` but lives deploy-side so ops can gate
    on an instruction set without depending on the instruction package being on
    ``sys.path``."""
    return INSTRUCTION_MODELS_DIR / slug / "model.json"

CONFIG_DIR = ASKADIA_ROOT / "config"
MODEL_GUIDS_YML = CONFIG_DIR / "model_guids.yml"

TABULAR_SCRIPTS_DIR = DEPLOY_DIR / "tabular_scripts"
