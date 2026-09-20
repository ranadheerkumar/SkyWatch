"""SkyWatch Cloud Abstraction Provider Module.

Factory functions and provider exports for storage and secrets.
"""

from __future__ import annotations

import os
from .base import SecretProvider, StorageProvider
from .local_provider import LocalEnvSecretProvider, LocalStorageProvider
from .azure_provider import AzureBlobStorageProvider, AzureKeyVaultSecretProvider
from .gcp_provider import GCPSecretManagerProvider, GCPStorageProvider
from .aws_provider import AWSSecretsManagerProvider, AWSS3StorageProvider

__all__ = [
    "StorageProvider",
    "SecretProvider",
    "LocalStorageProvider",
    "LocalEnvSecretProvider",
    "AzureBlobStorageProvider",
    "AzureKeyVaultSecretProvider",
    "GCPStorageProvider",
    "GCPSecretManagerProvider",
    "AWSS3StorageProvider",
    "AWSSecretsManagerProvider",
    "get_storage_provider",
    "get_secret_provider",
]


def get_storage_provider(provider_type: str | None = None) -> StorageProvider:
    """Return configured storage provider: local, azure, gcp, or aws."""
    choice = (provider_type or os.getenv("STORAGE_PROVIDER", "local")).lower().strip()
    if choice in ("azure", "azure_blob"):
        return AzureBlobStorageProvider()
    elif choice in ("gcp", "gcp_storage", "gcs"):
        return GCPStorageProvider()
    elif choice in ("aws", "aws_s3", "s3"):
        return AWSS3StorageProvider()
    return LocalStorageProvider()


def get_secret_provider(provider_type: str | None = None) -> SecretProvider:
    """Return configured secret provider: local_env, azure, gcp, or aws."""
    choice = (provider_type or os.getenv("SECRET_PROVIDER", "local_env")).lower().strip()
    if choice in ("azure", "azure_keyvault"):
        return AzureKeyVaultSecretProvider()
    elif choice in ("gcp", "gcp_secrets"):
        return GCPSecretManagerProvider()
    elif choice in ("aws", "aws_secrets"):
        return AWSSecretsManagerProvider()
    return LocalEnvSecretProvider()
