"""Utility functions for accessing environment variables with optional suppression of missing-variable errors."""
from __future__ import annotations

import os
from typing import Any, Optional


class VariableNotAssignedError(Exception):
    """Raised when a required environment variable has not been assigned."""


_SUPPRESS_FLAG_ENV_NAME = "SUPPRESS_VARIABLE_NOT_ASSIGNED_ERROR"
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _should_suppress_missing_variable() -> bool:
    value = os.getenv(_SUPPRESS_FLAG_ENV_NAME, "false")
    return str(value).strip().lower() in _TRUE_VALUES


def getenvval(key: str, default_value: Optional[Any] = None) -> Optional[Any]:
    """Retrieve an environment variable, optionally raising if it is missing."""
    value = os.getenv(key)
    if value is not None:
        return value
    if default_value is not None or _should_suppress_missing_variable():
        return default_value
    raise VariableNotAssignedError(f"{key} environment variable is not set")
