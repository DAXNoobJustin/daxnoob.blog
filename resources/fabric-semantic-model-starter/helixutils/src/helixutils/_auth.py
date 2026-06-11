"""Module to authenticate to fs sources"""

from helixutils._debug import get_logger
from helixutils._var import (
    global_variable,
    spark,
)

logger = get_logger(__name__)


def _set_spark_auth():
    """
    Configure Spark for **external** ADLS Gen2 access via AAD OAuth.

    Note: OneLake itself is accessed natively in Fabric using the notebook's
    workspace identity -- no Spark auth config is required for OneLake paths.
    This function illustrates wiring AAD OAuth for an external ADLS Gen2 account
    backed by a key-vault client certificate; supply your own OAuth
    token-provider class for ``fs.azure.account.oauth.provider.type``.
    """
    logger.debug("Setting Spark authentication configurations")
    ########## External ADLS Gen2 OAuth (OneLake is native -- see docstring) ##########

    provider_type = "<your-adls-oauth2-token-provider-class>"

    spark.conf.set("fs.azure.account.oauth.provider.type", provider_type)
    spark.conf.set("fs.azure.account.auth.akv.name", global_variable["vault_url"])
    spark.conf.set("fs.azure.account.auth.akv.certname", global_variable["app_data_cert_name"])
    spark.conf.set("fs.azure.account.auth.client.id", global_variable["app_data_client_id"])
    spark.conf.set("fs.azure.account.auth.tenant.id", global_variable["tenant_id"])

    spark.conf.set("spark.hadoop.fs.azure.account.oauth.provider.type", provider_type)
    spark.conf.set("spark.hadoop.fs.azure.account.auth.akv.name", global_variable["vault_url"])
    spark.conf.set("spark.hadoop.fs.azure.account.auth.akv.certname", global_variable["app_data_cert_name"])
    spark.conf.set("spark.hadoop.fs.azure.account.auth.client.id", global_variable["app_data_client_id"])
    spark.conf.set("spark.hadoop.fs.azure.account.auth.tenant.id", global_variable["tenant_id"])
