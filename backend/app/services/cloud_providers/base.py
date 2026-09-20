"""SkyWatch Cloud Abstraction Provider Interfaces.

Codifies the Cloud-Neutral Architecture defined in Sections 13-17 & 43 of the Master Architecture.
Shields core business logic from direct dependencies on Azure, GCP, or AWS SDKs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StorageProvider(ABC):
    """Abstract interface for object and artifact blob storage."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the cloud/local storage provider."""

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str, content_type: str = "application/octet-stream") -> str:
        """Upload a local file to object storage and return its public or internal URL."""

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Download a file from object storage to a local path."""

    @abstractmethod
    def get_signed_url(self, remote_path: str, expiry_seconds: int = 3600) -> str:
        """Generate a time-limited presigned URL for downloading the object."""

    @abstractmethod
    def delete_file(self, remote_path: str) -> bool:
        """Delete an object from storage."""

    @abstractmethod
    def list_files(self, prefix: str = "") -> list[str]:
        """List object keys matching the given prefix."""


class SecretProvider(ABC):
    """Abstract interface for enterprise secret and credential management."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the secret provider."""

    @abstractmethod
    def get_secret(self, secret_name: str, default: str | None = None) -> str | None:
        """Retrieve a secret value by name."""

    @abstractmethod
    def set_secret(self, secret_name: str, secret_value: str) -> bool:
        """Store or update a secret value."""

    @abstractmethod
    def delete_secret(self, secret_name: str) -> bool:
        """Delete a secret value."""
