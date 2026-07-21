"""In-process fixed-window rate limiter for login attempts.

Single-instance only (state lives in a module-level dict) — fine for the
current single-process SQLite deployment; would need a shared store
(e.g. Redis) behind multiple workers/instances.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from .env_utils import getenvval

_MAX_ATTEMPTS = int(getenvval("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 5))
_WINDOW_SECONDS = int(getenvval("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300))

_attempts: dict[str, list[float]] = defaultdict(list)


def check_login_rate_limit(key: str) -> None:
    """Raise 429 if `key` already used up its login attempts within the window."""
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS
    timestamps = [t for t in _attempts[key] if t > window_start]
    if len(timestamps) >= _MAX_ATTEMPTS:
        _attempts[key] = timestamps
        raise HTTPException(HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts. Please try again later.")
    timestamps.append(now)
    _attempts[key] = timestamps


def reset_login_rate_limit(key: str) -> None:
    """Clear recorded attempts for `key` (call after a successful login)."""
    _attempts.pop(key, None)
