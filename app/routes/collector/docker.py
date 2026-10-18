import json
import struct
from datetime import UTC, datetime

import httpx


def _parse_ts(raw: str) -> datetime:
    """RFC3339Nano -> aware UTC datetime (나노초는 마이크로초로 자른다)."""
    raw = raw.rstrip("Z")
    if "." in raw:
        head, frac = raw.split(".", 1)
        raw = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(raw).replace(tzinfo=UTC)


def _demux(data: bytes) -> bytes:
    out, i = [], 0
    while i + 8 <= len(data):
        size = struct.unpack(">I", data[i + 4 : i + 8])[0]
        out.append(data[i + 8 : i + 8 + size])
        i += 8 + size
    return b"".join(out)


class DockerClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=30)

    async def list_containers(self) -> list[dict]:
        res = await self._http.get("/containers/json")
        res.raise_for_status()
        return [
            {**c, "name": c["Names"][0].lstrip("/")} for c in res.json()
        ]

    async def logs(self, container_id: str, since: float) -> list[tuple[datetime, str]]:
        info = await self._http.get(f"/containers/{container_id}/json")
        info.raise_for_status()
        tty = bool(info.json().get("Config", {}).get("Tty"))
        res = await self._http.get(
            f"/containers/{container_id}/logs",
            params={"stdout": 1, "stderr": 1, "timestamps": 1, "since": f"{since:.6f}"},
        )
        res.raise_for_status()
        text = (res.content if tty else _demux(res.content)).decode("utf-8", "replace")
        out = []
        for line in text.splitlines():
            ts, _, msg = line.partition(" ")
            try:
                out.append((_parse_ts(ts), msg))
            except ValueError:
                continue
        return out

    async def events(self, since: float, until: float) -> list[dict]:
        res = await self._http.get(
            "/events",
            params={
                "since": f"{since:.6f}",
                "until": f"{until:.6f}",
                "filters": json.dumps(
                    {"type": ["container"], "event": ["die", "oom", "health_status"]}
                ),
            },
        )
        res.raise_for_status()
        return [json.loads(ln) for ln in res.text.splitlines() if ln.strip()]
