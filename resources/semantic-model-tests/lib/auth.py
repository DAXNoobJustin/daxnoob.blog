"""
Token-cached credential wrapper for Fabric + Power BI scopes.

Single source of truth for token acquisition (token caching, AzureCli
process_timeout bump for slow CI OIDC, optional interactive browser auth).
Used by the XMLA test runner.
"""

from __future__ import annotations

import threading
import time

from azure.identity import AzureCliCredential, InteractiveBrowserCredential

# OAuth scopes used across the dev surface.
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
PBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"

# Default Fabric API root (public). Callers may override per call site.
DEFAULT_FABRIC_API = "https://api.fabric.microsoft.com"

# Power BI's XMLA / Analysis Services endpoint only accepts USER tokens issued to a
# Power BI-registered client app. A token from the default azure-identity client or
# the Azure CLI (generic Azure clients) is rejected at AdomdConnection.Open() with
# "Authentication failed for all authenticators" -- even though the same token works
# for the Fabric REST workspace lookup. So for local interactive auth we mint the
# PBI_SCOPE (XMLA) token from the well-known Power BI native client below; the Fabric
# REST scope is NOT client-app gated and keeps the default interactive client.
# Service principals (CI) can't do interactive auth and use AzureCliCredential; the
# SP is already an approved Power BI client, so its token works for both scopes and
# the non-interactive path is unchanged. This is Microsoft's public Power BI native
# client id (the one DAX Studio / Tabular Editor use) -- not a secret.
_PBI_NATIVE_CLIENT_ID = "ea0616ba-638b-4df5-95b9-636659ae5121"


class Auth:
    """Caches OAuth tokens per scope. Thread-safe."""

    def __init__(self, *, interactive: bool = False) -> None:
        """
        Initialize the credential(s).

        Args:
            interactive: If True, use ``InteractiveBrowserCredential`` for a local
                browser sign-in (the XMLA scope is minted from the Power BI native
                client; see ``_PBI_NATIVE_CLIENT_ID``). If False, use
                ``AzureCliCredential`` with a 60 s ``process_timeout`` -- the path
                a service principal takes in CI, which cannot do interactive auth.

                The 10 s default was insufficient for a hosted CI agent:
                cold-cache ``az`` subprocess startup (first-call OIDC
                federated-token exchange) was observed at 15-48 s, causing
                ``CredentialUnavailableError`` despite valid SP auth.

        """
        if interactive:
            # Fabric REST is not client-app gated -> default interactive client.
            self.cred = InteractiveBrowserCredential()
            # PBI / XMLA IS client-app gated -> mint that scope from a Power BI client.
            self._pbi_cred = InteractiveBrowserCredential(client_id=_PBI_NATIVE_CLIENT_ID)
        else:
            # SPN / CI: no interactive auth. AzureCliCredential's SP token works for
            # both scopes (the SP is an approved Power BI client). process_timeout is
            # bumped from the 10s default because a hosted CI agent has been observed
            # taking 15-48s for cold-cache `az` subprocess startup (first-call OIDC
            # federated-token exchange), which would otherwise fail with
            # CredentialUnavailableError despite valid SP auth.
            self.cred = AzureCliCredential(process_timeout=60)
            self._pbi_cred = self.cred
        self._cache: dict[str, tuple[str, float]] = {}  # scope -> (token, expires_on)
        self._lock = threading.Lock()

    def headers(self, scope: str) -> dict[str, str]:
        """Return Authorization + Content-Type headers for the given scope."""
        return {"Authorization": f"Bearer {self.token(scope)}", "Content-Type": "application/json"}

    def token(self, scope: str) -> str:
        """
        Return a cached access token for `scope`, renewing as needed.

        Tokens are cached per-scope until 60 s before their stated expiry to
        avoid mid-call expiration. Thread-safe.
        """
        with self._lock:
            cached = self._cache.get(scope)
            if cached and cached[1] > time.time() + 60:  # 60s buffer
                return cached[0]
            cred = self._pbi_cred if scope == PBI_SCOPE else self.cred
            tok = cred.get_token(scope)
            self._cache[scope] = (tok.token, tok.expires_on)
            return tok.token

    def warm(self) -> None:
        """Pre-fetch tokens for both scopes (call before spawning threads)."""
        self.token(FABRIC_SCOPE)
        self.token(PBI_SCOPE)
