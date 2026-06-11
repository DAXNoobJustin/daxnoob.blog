"""
Module to interact with tokens, key vault, and secrets.

This module provides unified functionality for secret retrieval and token management
across different Azure environments, combining vault operations and secret access.
"""

from notebookutils import mssparkutils

from helixutils._debug import get_logger

logger = get_logger(__name__)


def get_helix_secret(secret_name):
    """
    Retrieve a secret from the default Helix key vault.

    Args:
        secret_name (str): The name of the secret to retrieve

    Returns:
        str: The secret value

    """
    try:
        # Use the production key vault as default
        vault_url = "https://your-keyvault.vault.azure.net/"

        return mssparkutils.credentials.getSecret(vault_url, secret_name)
    except Exception as e:
        logger.error(f"Failed to retrieve secret '{secret_name}': {e}")
        raise


def get_token(auth_resource, tenant_id=None, client_id=None, vault_url=None, cert_name=None):  # noqa: ARG001
    """
    Get an AAD token for the given audience.

    Uses the Fabric NotebookUtils credentials API, which returns a token for the
    identity the notebook runs as (the interactive user, or the pipeline's service
    principal). The optional ``tenant_id`` / ``client_id`` / ``vault_url`` /
    ``cert_name`` parameters are retained for signature compatibility with custom
    token-provider setups and are unused on the default Fabric path.
    """
    return mssparkutils.credentials.getToken(auth_resource)
