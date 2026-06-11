"""
Centralized debug logging utilities for helixutils.

This module provides debug-aware logging that ONLY affects helixutils loggers,
without interfering with global logging or other applications.

Debug Mode:
-----------
To enable verbose logging for helixutils functions only, set either:
- Environment variable: HELIXUTILS_DEBUG=true

Or enable it programmatically via `set_debug_mode(True)`.

When debug mode is DISABLED: Only WARNING and ERROR messages show for helixutils
When debug mode is ENABLED: DEBUG and INFO messages also show for helixutils (displayed as warnings)

"""

import logging
import os

_DEBUG_MODE: bool | None = None

# Configure helixutils logger with minimal format (message only)
_helix_logger = logging.getLogger("helixutils")
_helix_logger.setLevel(logging.INFO)
_helix_logger.propagate = False  # Don't inherit root logger format

_handler_exists = any(isinstance(handler, logging.StreamHandler) for handler in _helix_logger.handlers)
if not _handler_exists:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("helixutils %(message)s"))
    _helix_logger.addHandler(_handler)

# Suppress noisy py4j logs
logging.getLogger("py4j").setLevel(logging.WARNING)


def is_debug_mode() -> bool:
    """Check if debug mode is enabled."""
    if _DEBUG_MODE is not None:
        return bool(_DEBUG_MODE)

    # Check environment variable first
    return os.getenv("HELIXUTILS_DEBUG", "").lower() in ("true", "1", "yes", "on")


def set_debug_mode(enabled: bool | None) -> None:
    """
    Set helixutils debug mode programmatically.

    - True/False forces debug mode on/off.
    - None clears the override and falls back to HELIXUTILS_DEBUG.
    """
    global _DEBUG_MODE
    _DEBUG_MODE = enabled


class HelixDebugLogger:
    """Custom logger wrapper that respects helixutils debug mode only."""

    def __init__(self, logger):
        self._logger = logger

    def debug(self, msg, *args, **kwargs):
        """Only logs when debug mode is enabled."""
        if is_debug_mode():
            self._logger.info(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """Always logs."""
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)


def get_logger(name: str | None = None) -> HelixDebugLogger:
    """
    Get a debug-aware logger for helixutils that doesn't affect global logging.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Custom logger that respects helixutils debug mode without affecting other loggers

    """
    base_logger = logging.getLogger(name or "helixutils")
    return HelixDebugLogger(base_logger)
