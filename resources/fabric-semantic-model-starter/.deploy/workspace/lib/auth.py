"""
Token-cached credential wrapper for Fabric + Power BI scopes.

Single source of truth for token acquisition. Both `.deploy/workspace/debug_deploy.py`
and `semantic_model_tests/run_tests.py` instantiate Auth directly (token caching,
AzCli process_timeout bump for slow CI OIDC, optional interactive browser auth).
"""

from __future__ import annotations

import threading
import time

from azure.identity import AzureCliCredential, InteractiveBrowserCredential

# OAuth scopes used across the dev surface.
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
PBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"

# Default Fabric API root. Callers may override per call site.
DEFAULT_FABRIC_API = "https://api.fabric.microsoft.com"


class Auth:
    """Caches OAuth tokens per scope. Thread-safe."""

    def __init__(self, *, interactive: bool = False, credential=None) -> None:
        """
        Initialize the credential.

        Args:
            interactive: If True, use ``InteractiveBrowserCredential`` (browser
                popup; suited for local sessions). Default uses
                ``AzureCliCredential`` with a 60 s ``process_timeout``.

                The 10 s default was insufficient for the
                Validate_SemanticModelTests hosted agent: cold-cache
                ``az`` subprocess startup (first-call OIDC federated-token
                exchange) was observed at 15-48 s, causing
                ``CredentialUnavailableError`` despite valid SP auth.

            credential: Existing Azure credential object to wrap. Used by
                deploy operations so production and debug paths share token-
                cached REST helpers without changing their auth source.

        """
        # Bump process_timeout from the 10s default. The Validate_SemanticModelTests
        # hosted agent has been observed taking 15-48s for `az` subprocess startup
        # (cold cache, first-call OIDC federated-token exchange). At default
        # `az account get-access-token` would time out post-publish and fail
        # the run with CredentialUnavailableError despite valid SP auth.
        if credential is not None:
            self.cred = credential
        else:
            self.cred = (
                InteractiveBrowserCredential()
                if interactive
                else AzureCliCredential(process_timeout=60)
            )
        self._cache: dict[str, tuple[str, float]] = {}  # scope -> (token, expires_on)
        self._lock = threading.Lock()

    def headers(self, scope: str) -> dict[str, str]:
        """Return Authorization + Content-Type headers for the given scope."""
        return {"Authorization": f"Bearer {self.token(scope)}", "Content-Type": "application/json"}

    def token(self, scope: str) -> str:
        """
        Return a cached access token for `scope`, refreshing as needed.

        Tokens are cached per-scope until 60 s before their stated expiry to
        avoid mid-call expiration. Thread-safe.
        """
        with self._lock:
            cached = self._cache.get(scope)
            if cached and cached[1] > time.time() + 60:  # 60s buffer
                return cached[0]
            tok = self.cred.get_token(scope)
            self._cache[scope] = (tok.token, tok.expires_on)
            return tok.token

    def warm(self) -> None:
        """Pre-fetch tokens for both scopes (call before spawning threads)."""
        self.token(FABRIC_SCOPE)
        self.token(PBI_SCOPE)
