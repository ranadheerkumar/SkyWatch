"""Local Filesystem and Environment Providers.

Provides standard storage and secret capabilities for local development, Docker, and CI
with zero external cloud dependencies.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from .base import SecretProvider, StorageProvider

logger = logging.getLogger("skywatch.cloud.local")


class LocalStorageProvider(StorageProvider):
    """Stores execution artifacts and evidence directly on the local filesystem."""

    def __init__(self, base_dir: str | Path = "data/storage") -> None:
        self._base_path = Path(base_dir).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)

    @property
    def provider_name(self) -> str:
        return "local"

    def upload_file(self, local_path: str, remote_path: str, content_type: str = "application/octet-stream") -> str:
        source = Path(local_path)
        if not source.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        target = self._base_path / remote_path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return f"file://{target}"

    def download_file(self, remote_path: str, local_path: str) -> bool:
        target = self._base_path / remote_path.lstrip("/")
        if not target.exists():
            return False
        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, dest)
        return True

    def get_signed_url(self, remote_path: str, expiry_seconds: int = 3600) -> str:
        target = self._base_path / remote_path.lstrip("/")
        return f"/api/v1/evidence/file/{remote_path.lstrip('/')}"

    def delete_file(self, remote_path: str) -> bool:
        target = self._base_path / remote_path.lstrip("/")
        if target.exists():
            target.unlink()
            return True
        return False

    def list_files(self, prefix: str = "") -> list[str]:
        target_dir = self._base_path / prefix.lstrip("/")
        if not target_dir.exists():
            return []
        files = []
        for p in target_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self._base_path).as_posix()
                files.append(rel)
        return files


class LocalEnvSecretProvider(SecretProvider):
    """Resolves secrets from OS environment variables and local environment files."""

    @property
    def provider_name(self) -> str:
        return "local_env"

    def get_secret(self, secret_name: str, default: str | None = None) -> str | None:
        return os.getenv(secret_name, default)

    def set_secret(self, secret_name: str, secret_value: str) -> bool:
        os.environ[secret_name] = secret_value
        return True

    def delete_secret(self, secret_name: str) -> bool:
        if secret_name in os.environ:
            del os.environ[secret_name]
            return True
        return False
