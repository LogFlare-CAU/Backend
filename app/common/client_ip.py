"""The real client address of a request that came through the edge proxy.

Production traffic reaches the app through Cloudflare -> cloudflared -> Caddy, so
`request.client.host` is always the proxy's private address. Forwarded headers are
trusted only when the direct peer is private (the proxy, or a test client); a
request straight from a public address keeps its own address.
"""
from __future__ import annotations

import ipaddress

from fastapi import Request


def _is_private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def get_client_ip(request: Request) -> str:
    peer = request.client.host if request.client else ""
    if not _is_private(peer):
        return peer or "unknown"
    # Cloudflare sets this on every request it forwards and overwrites any copy
    # the client sent, so it is the most reliable source for WAN traffic.
    cf = request.headers.get("cf-connecting-ip", "").strip()
    if cf:
        return cf
    # LAN traffic: Caddy appends the peer it saw; the left-most entry is the client.
    xff = request.headers.get("x-forwarded-for", "")
    first = xff.split(",")[0].strip()
    return first or peer or "unknown"
