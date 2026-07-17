import time
import uuid

import jwt

from .env_utils import getenvval

algorithm = "HS256"
secret = getenvval("JWT_SECRET")


def generate_jwt(payload: dict, expire_seconds: int) -> str:
    """
    Generate a JWT with a standard ``exp`` claim (required).

    :param payload: Claims (must not rely on custom expire_at).
    :param expire_seconds: Lifetime from now in seconds; must be positive.
    """
    if expire_seconds <= 0:
        raise ValueError("expire_seconds must be positive")
    now = int(time.time())
    claims = dict(payload)
    claims["iat"] = now
    claims["exp"] = now + expire_seconds
    claims["jti"] = str(uuid.uuid4())
    return jwt.encode(claims, secret, algorithm=algorithm)


def decode_jwt(token: str) -> dict:
    """Decode and verify signature + standard ``exp`` (rejects expired tokens)."""
    return jwt.decode(token, secret, algorithms=[algorithm])
