"""Microsoft Azure Cloud Storage and Secret Providers.

Supports Azure Blob Storage and Azure Key Vault behind standard platform interfaces.
Uses optional runtime imports to prevent hard dependencies on Azure SDKs.
"""

from __future__ import annotations

import logging
import os
from .base import SecretProvider, StorageProvider

logger = logging.getLogger("skywatch.cloud.azure")


class AzureBlobStorageProvider(StorageProvider):
    """Stores execution artifacts in Azure Blob Storage."""

    def __init__(self, connection_string: str | None = None, container_name: str = "skywatch-artifacts") -> None:
        self._connection_string = connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        self._container_name = container_name

    @property
    def provider_name(self) -> str:
        return "azure_blob"

    def upload_file(self, local_path: str, remote_path: str, content_type: str = "application/octet-stream") -> str:
        if not self._connection_string:
            raise RuntimeError("Azure storage connection string not configured (AZURE_STORAGE_CONNECTION_STRING).")
        try:
            from azure.storage.blob import BlobServiceClient
            service_client = BlobServiceClient.from_connection_string(self._connection_string)
            blob_client = service_client.get_blob_client(container=self._container_name, blob=remote_path.lstrip("/"))
            with open(local_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            return blob_client.url
        except ImportError:
            raise RuntimeError("azure-storage-blob package is not installed.")

    def download_file(self, remote_path: str, local_path: str) -> bool:
        if not self._connection_string:
            return False
        try:
            from azure.storage.blob import BlobServiceClient
            service_client = BlobServiceClient.from_connection_string(self._connection_string)
            blob_client = service_client.get_blob_client(container=self._container_name, blob=remote_path.lstrip("/"))
            with open(local_path, "wb") as download_file:
                download_file.write(blob_client.download_blob().readall())
            return True
        except Exception as exc:
            logger.warning("Azure blob download failed: %s", exc)
            return False

    def get_signed_url(self, remote_path: str, expiry_seconds: int = 3600) -> str:
        return f"https://azure.blob.core.windows.net/{self._container_name}/{remote_path.lstrip('/')}"

    def delete_file(self, remote_path: str) -> bool:
        if not self._connection_string:
            return False
        try:
            from azure.storage.blob import BlobServiceClient
            service_client = BlobServiceClient.from_connection_string(self._connection_string)
            blob_client = service_client.get_blob_client(container=self._container_name, blob=remote_path.lstrip("/"))
            blob_client.delete_blob()
            return True
        except Exception:
            return False

    def list_files(self, prefix: str = "") -> list[str]:
        if not self._connection_string:
            return []
        try:
            from azure.storage.blob import BlobServiceClient
            service_client = BlobServiceClient.from_connection_string(self._connection_string)
            container_client = service_client.get_container_client(self._container_name)
            return [b.name for b in container_client.list_blobs(name_starts_with=prefix)]
        except Exception:
            return []


class AzureKeyVaultSecretProvider(SecretProvider):
    """Resolves secrets from Azure Key Vault."""

    def __init__(self, vault_url: str | None = None) -> None:
        self._vault_url = vault_url or os.getenv("AZURE_KEYVAULT_URL", "")

    @property
    def provider_name(self) -> str:
        return "azure_keyvault"

    def get_secret(self, secret_name: str, default: str | None = None) -> str | None:
        if not self._vault_url:
            return os.getenv(secret_name, default)
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            client = SecretClient(vault_url=self._vault_url, credential=DefaultAzureCredential())
            secret = client.get_secret(secret_name.replace("_", "-"))
            return secret.value or default
        except Exception:
            return os.getenv(secret_name, default)

    def set_secret(self, secret_name: str, secret_value: str) -> bool:
        if not self._vault_url:
            return False
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            client = SecretClient(vault_url=self._vault_url, credential=DefaultAzureCredential())
            client.set_secret(secret_name.replace("_", "-"), secret_value)
            return True
        except Exception:
            return False

    def delete_secret(self, secret_name: str) -> bool:
        return False
