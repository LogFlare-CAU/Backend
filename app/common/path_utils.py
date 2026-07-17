"""Filesystem path helpers (logfile allowlisting)."""
from __future__ import annotations

import os

from fastapi import HTTPException
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN

from common.env_utils import getenvval


def _default_allowed_roots() -> list[str]:
    roots: list[str] = []
    for candidate in ("/logs", os.path.join(os.getcwd(), "logs")):
        real = os.path.realpath(candidate)
        if real not in roots:
            roots.append(real)
    return roots


def allowed_log_roots() -> list[str]:
    raw = getenvval("LOGFLARE_LOG_ROOTS", "") or ""
    roots = [os.path.realpath(p.strip()) for p in raw.split(",") if p.strip()]
    return roots or _default_allowed_roots()


def assert_allowed_log_path(path: str, *, must_exist: bool = True) -> str:
    """
    Resolve ``path`` and ensure it stays under an allowed log root.
    Raises HTTPException on violation.
    """
    if not path or not str(path).strip():
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Log file path is required",
        )
    real = os.path.realpath(path)
    roots = allowed_log_roots()
    for root in roots:
        if real == root or real.startswith(root + os.sep):
            if must_exist and not os.path.isfile(real):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"Log file path does not exist or is not a file: {path}",
                )
            return real
    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN,
        detail="Log file path is outside allowed LOGFLARE_LOG_ROOTS",
    )
