"""Ingest v2: logfile link, raw payload, level normalisation."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from common.sqlsession import async_session
from routes.logs.model import Errorlog


async def _post(client: AsyncClient, name: str, token: str, **extra):
    body = {"errortype": "ValueError", "level": "ERROR", "message": "boom", "test": False}
    body.update(extra)
    res = await client.post(
        "/log/error",
        headers={"Project": name, "ProjectKey": f"Bearer {token}"},
        json=body,
    )
    assert res.status_code == 204, res.text
    return res


async def _rows():
    async with async_session() as session:
        return (await session.execute(select(Errorlog))).scalars().all()


async def _add_logfile(client, admin_token, project_id, sample_logfile) -> int:
    res = await client.post(
        f"/project/{project_id}/logfile",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "app.log", "path": str(sample_logfile)},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


@pytest.mark.asyncio
async def test_ingest_legacy_payload_still_204(client, project_with_key):
    name, token, _ = project_with_key
    await _post(client, name, token)
    rows = await _rows()
    assert len(rows) == 1
    assert rows[0].logfile_id is None
    assert rows[0].raw is None


@pytest.mark.asyncio
async def test_ingest_links_logfile_by_name(
    client, admin_token, project_with_key, sample_logfile
):
    name, token, project_id = project_with_key
    lid = await _add_logfile(client, admin_token, project_id, sample_logfile)
    await _post(client, name, token, logfile="app.log")
    assert (await _rows())[0].logfile_id == lid


@pytest.mark.asyncio
async def test_ingest_unknown_logfile_is_null(client, project_with_key):
    name, token, _ = project_with_key
    await _post(client, name, token, logfile="nope.log")
    assert (await _rows())[0].logfile_id is None


@pytest.mark.asyncio
async def test_ingest_stores_raw_truncated(client, project_with_key):
    name, token, _ = project_with_key
    await _post(client, name, token, raw="x" * 70_000)
    assert len((await _rows())[0].raw) == 65_536


@pytest.mark.asyncio
async def test_ingest_uppercases_level(client, project_with_key):
    name, token, _ = project_with_key
    await _post(client, name, token, level="error")
    assert (await _rows())[0].level == "ERROR"


@pytest.mark.asyncio
async def test_delete_logfile_keeps_errors(
    client, admin_token, project_with_key, sample_logfile
):
    name, token, project_id = project_with_key
    lid = await _add_logfile(client, admin_token, project_id, sample_logfile)
    await _post(client, name, token, logfile="app.log")
    res = await client.delete(
        f"/project/{project_id}/logfile/{lid}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200, res.text
    rows = await _rows()
    assert len(rows) == 1
    assert rows[0].logfile_id is None
