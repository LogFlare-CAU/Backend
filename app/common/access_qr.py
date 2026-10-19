"""관리자용 CF Access 로그인 QR 재료 — 토큰 파일 읽기, QR 내용, SVG.

앱 전용 Access 서비스 토큰의 secret 은 QR(SVG) 안에만 존재해야 한다. 로그·예외 메시지에 넣지 않는다.
segno 는 QR 을 만들 때만 가져온다(옛 이미지로 새 코드가 떠도 기동은 되도록).
"""
from __future__ import annotations

import io
import json


class QrLibMissing(Exception):
    """segno 가 설치되어 있지 않다."""


def load_qr_token(path: str | None) -> tuple[str, str] | None:
    """확장 token.txt 와 같은 두 줄 형식에서 (client id, secret). 없거나 틀리면 None."""
    if not path:
        return None
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return None
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            found[key.strip().lower()] = value.strip()
    cid = found.get("cf-access-client-id", "")
    secret = found.get("cf-access-client-secret", "")
    if not cid or not secret:
        return None
    return cid, secret


def qr_payload(server: str, client_id: str, secret: str) -> str:
    return json.dumps(
        {"v": 1, "server": server, "id": client_id, "secret": secret},
        separators=(",", ":"),
        ensure_ascii=False,
    )


def qr_svg(payload: str) -> str:
    try:
        import segno
    except ImportError:
        raise QrLibMissing() from None
    qr = segno.make(payload, error="m")
    buf = io.BytesIO()
    # svg_inline 은 xmlns 를 빼므로 save(svgns=True) 로 SVG 네임스페이스를 붙인다 (웹 화면이 image/svg+xml 로 파싱)
    # omitsize: width/height 대신 viewBox 를 써서 웹 화면이 줄여 그릴 때 잘리지 않게 한다
    qr.save(buf, kind="svg", xmldecl=False, svgns=True, nl=False, border=2, scale=6, omitsize=True,
            dark="#191F28", light="#FFFFFF")
    return buf.getvalue().decode("utf-8")


def mask_client_id(client_id: str) -> str:
    """`.access` 접미사를 뺀 앞 4 · 뒤 4 글자 (짧으면 전부 가린다)."""
    base = client_id[: -len(".access")] if client_id.lower().endswith(".access") else client_id
    if len(base) <= 8:
        return "…"
    return f"{base[:4]}…{base[-4:]}"
