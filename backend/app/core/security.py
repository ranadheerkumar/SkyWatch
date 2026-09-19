import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv

from app.core.config import settings


# Load backend configuration before the signing key is evaluated. This keeps
# tokens valid when the API is started from a different working directory.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
TOKEN_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


def hash_password(password: str) -> str:
	salt = os.urandom(16)
	digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
	return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
	try:
		algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
		candidate = hashlib.pbkdf2_hmac(algorithm.removeprefix("pbkdf2_"), password.encode(), bytes.fromhex(salt_hex), int(iterations))
		return hmac.compare_digest(candidate.hex(), digest_hex)
	except (ValueError, TypeError):
		return False


def create_access_token(subject: str) -> str:
	expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
	return jwt.encode({"sub": subject, "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
	payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
	subject = payload.get("sub")
	if not subject:
		raise ValueError("Token subject is missing")
	return str(subject)
