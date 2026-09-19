import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class IntegrationSecretError(RuntimeError):
    pass


def _fernet() -> Fernet:
    secret_key = settings.SECRET_KEY.strip()
    if not secret_key:
        raise IntegrationSecretError("SECRET_KEY is required to protect integration credentials")
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())
    return Fernet(derived_key)


def encrypt_integration_secret(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise IntegrationSecretError("Integration credential cannot be empty")
    return _fernet().encrypt(normalized.encode("utf-8")).decode("ascii")


def decrypt_integration_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as error:
        raise IntegrationSecretError("Integration credential could not be decrypted") from error
