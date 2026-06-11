"""
HelixData Utilities

Provides common tools for developing in Microsoft Fabric Spark environments.
This package includes utilities for data processing, monitoring, security, and analytics workflows.

Main modules:
- helix_read: Data reading utilities
- helix_check: PyDeequ-based data-quality checks (CheckConfig)
- helix_monitoring: Monitoring, logging, and incident management
- helix_vault: Azure Key Vault integration
- helix_delta: Delta Lake operations
- helix_tabular: Tabular model processing

DataFrame extensions installed on import (see _dataframe_monkeypatch):
write_delta, select_except, to_view, to_staged_view.
Config accessors: connection, global_variable.
"""

# Import all public functions from modules
from helixutils import (
    _auth,
    _dataframe_monkeypatch,
    helix_check,
    helix_delta,
    helix_monitoring,
    helix_read,
    helix_tabular,
    helix_vault,
)
from helixutils._var import connection, global_variable
from helixutils.helix_check import CheckConfig

# Initialize package
_auth._set_spark_auth()
_dataframe_monkeypatch.initialize()

__all__ = [
    "CheckConfig",
    "connection",
    "global_variable",
    "helix_check",
    "helix_delta",
    "helix_monitoring",
    "helix_read",
    "helix_tabular",
    "helix_vault",
]
