"""Unit tests for path allowlisting and JWT helpers."""
import os
import time

import jwt
import pytest
from fastapi import HTTPException

from common import jwt_utils
from common.jwt_utils import decode_jwt, generate_jwt
from common.path_utils import assert_allowed_log_path


def test_generate_jwt_requires_positive_ttl():
    with pytest.raises(ValueError):
        generate_jwt({"idx": 1}, expire_seconds=0)


def test_generate_and_decode_jwt_roundtrip():
    token = generate_jwt({"idx": 7, "perm": 0}, expire_seconds=60)
    claims = decode_jwt(token)
    assert claims["idx"] == 7
    assert claims["exp"] - claims["iat"] == 60
    assert claims["jti"]


def test_decode_rejects_expired(monkeypatch):
    token = jwt.encode(
        {
            "idx": 1,
            "iat": int(time.time()) - 50,
            "exp": int(time.time()) - 1,
            "jti": "x",
        },
        jwt_utils.secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_jwt(token)


def test_assert_allowed_log_path_accepts_fixture_file(sample_logfile):
    real = assert_allowed_log_path(str(sample_logfile), must_exist=True)
    assert os.path.isfile(real)


def test_assert_allowed_log_path_rejects_outside(tmp_path):
    outside = tmp_path / "escape.log"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        assert_allowed_log_path(str(outside), must_exist=True)
    assert exc.value.status_code == 403


def test_assert_allowed_log_path_rejects_missing(sample_logfile):
    missing = sample_logfile.parent / "does-not-exist.log"
    with pytest.raises(HTTPException) as exc:
        assert_allowed_log_path(str(missing), must_exist=True)
    assert exc.value.status_code == 400
