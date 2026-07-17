"""Misc API / envelope behavior."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_unhandled_error_hides_traceback(client: AsyncClient):
    from main import app

    async def boom():
        raise RuntimeError("secret internals")

    app.add_api_route("/__test_boom", boom, methods=["GET"])
    res = await client.get("/__test_boom")
    assert res.status_code == 500
    body = res.json()
    assert body["success"] is False
    assert body.get("data") in (None, {})
    assert "traceback" not in (body.get("data") or {})
    assert "secret internals" not in res.text


@pytest.mark.asyncio
async def test_root_html(client: AsyncClient):
    res = await client.get("/")
    assert res.status_code == 200
    assert "html" in res.headers.get("content-type", "").lower() or "<" in res.text


@pytest.mark.asyncio
async def test_validation_error_envelope(client: AsyncClient, admin_token: str):
    res = await client.post(
        "/user/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"username": "ab", "password": "short"},  # fails min lengths
    )
    assert res.status_code == 422
    body = res.json()
    assert body["success"] is False
    assert body["error_code"] == 422
    assert "errors" in (body.get("data") or {})


@pytest.mark.asyncio
async def test_fcm_data_returns_minimal_shape(client: AsyncClient, admin_token: str):
    res = await client.get(
        "/fcm/data",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    # empty config when FCM file unset — keys still present / nulls ok
    assert isinstance(data, dict)
    for key in (
        "project_id",
        "messaging_sender_id",
        "mobilesdk_app_id",
        "package_name",
        "api_key",
    ):
        assert key in data
