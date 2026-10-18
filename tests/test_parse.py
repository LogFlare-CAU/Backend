from datetime import UTC, datetime
from routes.collector.parse import LineAssembler, classify, fingerprint, mask_secrets, normalize

T = datetime(2026, 10, 18, tzinfo=UTC)

def test_mask_secrets():
    s = mask_secrets('GET /x?token=abc123&key=K9 Authorization: Bearer eyJhbGc.x.y https://u:pw@h/p password: hunter2')
    for leak in ("abc123", "K9", "eyJhbGc", "u:pw@", "hunter2"):
        assert leak not in s
    assert s.count("***") >= 5

def test_normalize_collapses_variants():
    a = "PUT /applications/{app_id}/commands Has exceeded its ratelimit (2)! Reset in 59.967 seconds"
    b = "PUT /applications/{app_id}/commands Has exceeded its ratelimit (2)! Reset in 59.975 seconds"
    assert normalize(a) == normalize(b)
    assert fingerprint("x", "WARNING", a) == fingerprint("x", "WARNING", b)
    assert normalize('dial tcp 172.31.0.8:3000: connect: connection refused') == normalize('dial tcp 172.31.0.9:3000: connect: connection refused')

def test_fingerprint_differs_by_source_and_level():
    assert fingerprint("a", "ERROR", "boom") != fingerprint("b", "ERROR", "boom")
    assert fingerprint("a", "ERROR", "boom") != fingerprint("a", "WARNING", "boom")
    assert len(fingerprint("a", "ERROR", "boom")) == 16

def test_classify():
    assert classify('{"level":"error","logger":"http.log.error","msg":"dial tcp: lookup hub: i/o timeout"}') == ("ERROR", None)
    assert classify('{"level":"info","logger":"http.log.access","msg":"handled request"}') is None
    assert classify('{"level":"warn","logger":"http.handlers.reverse_proxy","msg":"aborting"}') == ("WARNING", None)
    assert classify('INFO:     172.31.0.11:48844 - "GET / HTTP/1.1" 200 OK') is None
    assert classify('INFO:     1.2.3.4:5 - "GET /error HTTP/1.1" 500 Internal Server Error') is None
    assert classify("2026-10-18 ERROR something broke")[0] == "ERROR"
    assert classify("all good") is None

def test_traceback_is_one_entry():
    asm = LineAssembler()
    out = []
    for line in [
        "Traceback (most recent call last):",
        '  File "/app/x.py", line 3, in f',
        "    raise last_error",
        "src.toss.errors.TossAPIError: stock-not-found: 종목을 찾을 수 없습니다.",
        "INFO next request",
    ]:
        out += asm.feed(T, line)
    out += asm.flush()
    assert len(out) == 1
    e = out[0]
    assert e.level == "ERROR" and e.errortype == "TossAPIError"
    assert "raise last_error" in e.message
    assert normalize(e.message).startswith("src.toss.errors.TossAPIError")
