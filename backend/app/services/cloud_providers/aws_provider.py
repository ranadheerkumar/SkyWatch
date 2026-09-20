"""Amazon Web Services (AWS) Storage and Secret Providers.

Supports AWS S3 and AWS Secrets Manager behind standard platform interfaces.
Uses optional runtime imports to prevent hard dependencies on boto3.
"""

from __future__ import annotations

import logging
import os
from .base import SecretProvider, StorageProvider

logger = logging.getLogger("skywatch.cloud.aws")


class AWSS3StorageProvider(StorageProvider):
    """Stores execution artifacts in Amazon Simple Storage Service (S3)."""

    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or os.getenv("AWS_S3_BUCKET", "skywatch-artifacts")

    @property
    def provider_name(self) -> str:
        return "aws_s3"

    def upload_file(self, local_path: str, remote_path: str, content_type: str = "application/octet-stream") -> str:
        try:
            import boto3
            s3 = boto3.client("s3")
            key = remote_path.lstrip("/")
            s3.upload_file(local_path, self._bucket_name, key, ExtraArgs={"ContentType": content_type})
            return f"https://{self._bucket_name}.s3.amazonaws.com/{key}"
        except ImportError:
            raise RuntimeError("boto3 package is not installed.")

    def download_file(self, remote_path: str, local_path: str) -> bool:
        try:
            import boto3
            s3 = boto3.client("s3")
            s3.download_file(self._bucket_name, remote_path.lstrip("/"), local_path)
            return True
        except Exception as exc:
            logger.warning("AWS S3 download failed: %s", exc)
            return False

    def get_signed_url(self, remote_path: str, expiry_seconds: int = 3600) -> str:
        try:
            import boto3
            s3 = boto3.client("s3")
            return s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket_name, "Key": remote_path.lstrip("/")},
                ExpiresIn=expiry_seconds,
            )
        except Exception:
            return f"https://{self._bucket_name}.s3.amazonaws.com/{remote_path.lstrip('/')}"

    def delete_file(self, remote_path: str) -> bool:
        try:
            import boto3
            s3 = boto3.client("s3")
            s3.delete_object(Bucket=self._bucket_name, Key=remote_path.lstrip("/"))
            return True
        except Exception:
            return False

    def list_files(self, prefix: str = "") -> list[str]:
        try:
            import boto3
            s3 = boto3.client("s3")
            res = s3.list_objects_v2(Bucket=self._bucket_name, Prefix=prefix.lstrip("/"))
            return [item["Key"] for item in res.get("Contents", [])]
        except Exception:
            return []


class AWSSecretsManagerProvider(SecretProvider):
    """Resolves secrets from AWS Secrets Manager."""

    def __init__(self, region_name: str | None = None) -> None:
        self._region_name = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    @property
    def provider_name(self) -> str:
        return "aws_secrets"

    def get_secret(self, secret_name: str, default: str | None = None) -> str | None:
        try:
            import boto3
            client = boto3.client("secretsmanager", region_name=self._region_name)
            response = client.get_secret_value(SecretId=secret_name)
            return response.get("SecretString", default)
        except Exception:
            return os.getenv(secret_name, default)

    def set_secret(self, secret_name: str, secret_value: str) -> bool:
        return False

    def delete_secret(self, secret_name: str) -> bool:
        return False
