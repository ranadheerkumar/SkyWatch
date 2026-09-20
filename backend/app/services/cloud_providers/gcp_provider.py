"""Google Cloud Platform (GCP) Storage and Secret Providers.

Supports Google Cloud Storage (GCS) and GCP Secret Manager behind standard platform interfaces.
Uses optional runtime imports to prevent hard dependencies on Google Cloud SDKs.
"""

from __future__ import annotations

import logging
import os
from .base import SecretProvider, StorageProvider

logger = logging.getLogger("skywatch.cloud.gcp")


class GCPStorageProvider(StorageProvider):
    """Stores execution artifacts in Google Cloud Storage (GCS)."""

    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or os.getenv("GCP_STORAGE_BUCKET", "skywatch-artifacts")

    @property
    def provider_name(self) -> str:
        return "gcp_storage"

    def upload_file(self, local_path: str, remote_path: str, content_type: str = "application/octet-stream") -> str:
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(self._bucket_name)
            blob = bucket.blob(remote_path.lstrip("/"))
            blob.upload_from_filename(local_path, content_type=content_type)
            return blob.public_url
        except ImportError:
            raise RuntimeError("google-cloud-storage package is not installed.")

    def download_file(self, remote_path: str, local_path: str) -> bool:
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(self._bucket_name)
            blob = bucket.blob(remote_path.lstrip("/"))
            blob.download_to_filename(local_path)
            return True
        except Exception as exc:
            logger.warning("GCP blob download failed: %s", exc)
            return False

    def get_signed_url(self, remote_path: str, expiry_seconds: int = 3600) -> str:
        return f"https://storage.googleapis.com/{self._bucket_name}/{remote_path.lstrip('/')}"

    def delete_file(self, remote_path: str) -> bool:
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(self._bucket_name)
            blob = bucket.blob(remote_path.lstrip("/"))
            blob.delete()
            return True
        except Exception:
            return False

    def list_files(self, prefix: str = "") -> list[str]:
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(self._bucket_name)
            return [b.name for b in bucket.list_blobs(prefix=prefix)]
        except Exception:
            return []


class GCPSecretManagerProvider(SecretProvider):
    """Resolves secrets from Google Cloud Secret Manager."""

    def __init__(self, project_id: str | None = None) -> None:
        self._project_id = project_id or os.getenv("GCP_PROJECT_ID", "")

    @property
    def provider_name(self) -> str:
        return "gcp_secrets"

    def get_secret(self, secret_name: str, default: str | None = None) -> str | None:
        if not self._project_id:
            return os.getenv(secret_name, default)
        try:
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self._project_id}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception:
            return os.getenv(secret_name, default)

    def set_secret(self, secret_name: str, secret_value: str) -> bool:
        return False

    def delete_secret(self, secret_name: str) -> bool:
        return False
