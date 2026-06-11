"""Module to store common variables"""

import os
import random
import time
from contextlib import suppress

from notebookutils import variableLibrary
from pyspark.sql import SparkSession

from helixutils._debug import get_logger

logger = get_logger(__name__)


def _retry_with_backoff(
    func,
    *,
    tries: int = 5,
    base_delay_s: float = 0.2,
    max_delay_s: float = 5.0,
    retry_on=(Exception,),
    no_retry_if=None,
    on_retry=None,
):
    """
    Retry helper with exponential backoff and jitter.

    - Retries up to `tries` times.
    - Uses exponential backoff: base_delay * 2^(attempt-1), capped at max_delay.
    - Adds small random jitter to reduce thundering herd.
    - If `no_retry_if` is a callable that returns True for an exception, raises immediately.
    """
    last_exc = None
    for attempt in range(1, tries + 1):
        try:
            return func()
        except retry_on as exc:
            if no_retry_if is not None and no_retry_if(exc):
                raise
            last_exc = exc
            if attempt >= tries:
                break

            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            delay = delay * (0.8 + 0.4 * random.random())

            if on_retry is not None:
                with suppress(Exception):
                    on_retry(exc, attempt, tries, delay)

            time.sleep(delay)

    raise last_exc


class CachedVariableLibrary:
    """Wrapper around a single Fabric Variable Library with dict-like access."""

    def __init__(self, library_name):
        self._library_name = library_name
        self._cache = {}
        self._base_delay_s = float(str(spark.conf.get("helixutils.variablelibrary.retry_base_delay", "0.2")))
        self._retry_count = int(str(spark.conf.get("helixutils.variablelibrary.retry_count", "5")))

    @staticmethod
    def _is_not_found(exc):
        """Return True if the exception is a definitive not-found (not retryable)."""
        msg = str(exc)
        return "VariableNotFoundException" in msg or "VariableLibraryNotFound" in msg

    def _resolve(self, key):
        """Resolve a single variable by name via the public get() API."""
        ref = f"$(/**/{self._library_name}/{key})"
        try:
            return _retry_with_backoff(
                lambda: variableLibrary.get(ref),
                tries=self._retry_count,
                base_delay_s=self._base_delay_s,
                retry_on=(Exception,),
                no_retry_if=self._is_not_found,
                on_retry=lambda exc, attempt, tries, delay: logger.warning(
                    "Failed to resolve '%s/%s' (attempt %s/%s). Retrying in %.2fs: %s",
                    self._library_name,
                    key,
                    attempt,
                    tries,
                    delay,
                    exc,
                ),
            )
        except Exception as exc:
            if self._is_not_found(exc):
                msg = f"Variable '{key}' not found in library '{self._library_name}'"
                raise KeyError(msg) from None
            raise

    def __getitem__(self, key):
        if key in self._cache:
            return self._cache[key]

        value = self._resolve(key)
        self._cache[key] = value
        return value

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def get(self, key, default=None):
        """Return the variable value, or *default* if not found."""
        try:
            return self[key]
        except KeyError:
            return default

    def clear_cache(self):
        """Clear all cached values so the next access re-fetches from the API."""
        self._cache.clear()


spark = SparkSession.builder.getOrCreate()

# Set SPARK_VERSION for pydeequ compatibility (required before pydeequ import)
if "SPARK_VERSION" not in os.environ:
    os.environ["SPARK_VERSION"] = spark.version[:3]  # e.g., "3.5" from "3.5.0"

global_variable = CachedVariableLibrary("global")


connection = CachedVariableLibrary("fs_connections")

linked_service = CachedVariableLibrary("linked_services")
