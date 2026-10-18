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


def test_mask_prefixed_and_json_keys():
    for src, leak in [
        ("access_token=abc1", "abc1"), ("client_secret=zz", "zz"), ("refresh_token=rt9", "rt9"),
        ("SECRET_KEY=abcq", "abcq"), ('{"password": "hunter2"}', "hunter2"), ("{'api_key':'k77'}", "k77"),
    ]:
        out = mask_secrets(src)
        assert leak not in out and "***" in out, src


def _run(lines):
    asm = LineAssembler()
    out = []
    for ln in lines:
        out += asm.feed(T, ln)
    return out + asm.flush()


def test_traceback_nonstandard_exception_names():
    for exc, et in [("psycopg2.errors.UniqueViolation: dup key", "UniqueViolation"), ("socket.timeout: timed out", "timeout")]:
        out = _run(["Traceback (most recent call last):", '  File "x.py", line 1, in f', "    boom()", exc, "INFO next"])
        assert len(out) == 1 and out[0].errortype == et and exc in out[0].message
        assert normalize(out[0].message).startswith(exc.split(":")[0])


def test_chained_exception_is_one_entry():
    out = _run([
        "Traceback (most recent call last):", '  File "x.py", line 1, in f', "    a()", "ValueError: bad",
        "", "During handling of the above exception, another exception occurred:", "",
        "Traceback (most recent call last):", '  File "x.py", line 5, in g', "    b()", "RuntimeError: wrapped",
        "INFO next",
    ])
    assert len(out) == 1 and out[0].errortype == "RuntimeError"
    assert "ValueError: bad" in out[0].message
    assert normalize(out[0].message).startswith("RuntimeError")
