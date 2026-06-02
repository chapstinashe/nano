import logging
import os
from typing import Mapping

logger = logging.getLogger(__name__)

VAULT_SECRET_MAP: dict[str, str] = {
    "JWT_SECRET_KEY": "jwt-secret-key",
    "AZURE_OPENAI_API_KEY": "azure-openai-api-key",
    "COSMOS_KEY": "cosmos-key",
    "AZURE_STORAGE_CONNECTION_STRING": "azure-storage-connection-string",
}


def _build_credential():
    try:
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    except ImportError as exc:
        raise ImportError(
            "azure-identity is required when AZURE_KEY_VAULT_URL is set"
        ) from exc

    client_id = (os.getenv("AZURE_CLIENT_ID") or "").strip()
    if client_id:
        logger.info("Using user-assigned managed identity for Key Vault")
        return ManagedIdentityCredential(client_id=client_id)
    logger.info("Using DefaultAzureCredential for Key Vault (system MI, Azure CLI, etc.)")
    return DefaultAzureCredential()


def load_key_vault_secrets() -> Mapping[str, str]:
    vault_url = (os.getenv("AZURE_KEY_VAULT_URL") or "").strip()
    if not vault_url:
        return {}

    try:
        from azure.keyvault.secrets import SecretClient
    except ImportError as exc:
        logger.warning(
            "AZURE_KEY_VAULT_URL is set but azure-keyvault-secrets is not installed: %s",
            exc,
        )
        return {}

    try:
        credential = _build_credential()
    except ImportError as exc:
        logger.warning(
            "AZURE_KEY_VAULT_URL is set but azure-identity is not installed: %s",
            exc,
        )
        return {}

    client = SecretClient(vault_url=vault_url, credential=credential)
    loaded: dict[str, str] = {}
    for env_name, secret_name in VAULT_SECRET_MAP.items():
        if os.getenv(env_name):
            continue
        try:
            value = client.get_secret(secret_name).value
            if value:
                loaded[env_name] = value
        except Exception:
            logger.debug("Key Vault secret not found: %s", secret_name)
    return loaded


def apply_key_vault_secrets() -> None:
    for env_name, value in load_key_vault_secrets().items():
        os.environ[env_name] = value
        logger.info("Loaded secret from Key Vault: %s", env_name)
