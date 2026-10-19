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


def test_mask_does_not_overmask_identifiers():
    for src in ["KeyError: user_id", "monkey=1", "keyboard: 3"]:
        assert mask_secrets(src) == src


def test_hex_address_normalized():
    a = "<Foo object at 0x7f3a9c1d2e50>"
    b = "<Foo object at 0x7fb1020304a0>"
    assert normalize(a) == normalize(b) and "<hex>" in normalize(a)
    assert fingerprint("x", "ERROR", a) == fingerprint("x", "ERROR", b)


def test_mask_camel_case_keys():
    assert "abc" not in mask_secrets("accessToken=abc") and "abc" not in mask_secrets('{"apiKey": "abc"}')


def test_mask_secrets_linear_on_long_words():
    import time

    t = time.perf_counter()
    out = mask_secrets("y" * 65_536 + " password=hunter2 " + "z" * 65_536)
    assert time.perf_counter() - t < 2.0
    assert "hunter2" not in out


# --- #31: 대표 줄, 이어 붙이기, 헤더 합치기, 잘린 트레이스백 ---
from routes.collector.parse import headline  # noqa: E402

TB = ["Traceback (most recent call last):", '  File "x.py", line 1, in f', "    boom()", "ValueError: bad 42"]


def test_headline_uses_exception_line():
    assert headline("\n".join(TB)) == "ValueError: bad 42"
    assert headline("ERROR:    Exception in ASGI application\n" + "\n".join(TB)) == "ValueError: bad 42"
    assert headline("plain first\nsecond") == "plain first"
    assert headline("") == ""


def test_headline_exception_group_and_truncated():
    eg = "\n".join(TB[:3] + ["ExceptionGroup: two (2 sub-exceptions)", "  +-+---- 1 ----", "    | ValueError: a"])
    assert headline(eg) == "ExceptionGroup: two (2 sub-exceptions)"
    # 예외 줄이 없는 잘린 트레이스백은 마지막 줄
    assert headline("\n".join(TB[:3])) == "    boom()".strip()


def test_access_log_http2_and_3_ignored():
    assert classify('INFO:     1.2.3.4:5 - "GET /error HTTP/2" 500 Internal Server Error') is None
    assert classify('INFO:     1.2.3.4:5 - "GET /error HTTP/2.0" 500 Internal Server Error') is None
    assert classify('INFO:     1.2.3.4:5 - "GET /error HTTP/3" 502 Bad Gateway') is None


def test_error_header_merged_with_traceback():
    out = _run(["ERROR:    Exception in ASGI application", *TB, "INFO next"])
    assert len(out) == 1
    assert out[0].errortype == "ValueError" and out[0].message.startswith("ERROR:    Exception in ASGI")
    # 지문은 헤더가 없을 때와 같다 (기존 묶음 유지)
    assert fingerprint("s", "ERROR", out[0].message) == fingerprint("s", "ERROR", "\n".join(TB))


def test_error_line_not_followed_by_traceback_stays_alone():
    out = _run(["ERROR one", "ERROR two", "INFO fine"])
    assert [e.message for e in out] == ["ERROR one", "ERROR two"]


def test_truncated_traceback_does_not_eat_next_log_line():
    out = _run([*TB[:3], "INFO:     1.2.3.4:5 - \"GET / HTTP/1.1\" 200 OK", "ERROR later"])
    assert [e.message.splitlines()[0] for e in out] == ["Traceback (most recent call last):", "ERROR later"]
    assert out[0].errortype is None
    out = _run([*TB[:3], "2026-10-18 12:00:00 ERROR db down"])
    assert len(out) == 2 and out[1].message == "2026-10-18 12:00:00 ERROR db down"


def test_bare_syntax_error_without_traceback_header():
    out = _run(['  File "/app/main.py", line 3', "    x = (", "        ^", "SyntaxError: '(' was never closed", "INFO next"])
    assert len(out) == 1 and out[0].errortype == "SyntaxError"
    assert headline(out[0].message) == "SyntaxError: '(' was never closed"


def test_syntax_error_caret_inside_traceback():
    out = _run(["Traceback (most recent call last):", '  File "a.py", line 3, in <module>', "    import b",
                '  File "b.py", line 1', "    x = (", "        ^^^", "SyntaxError: '(' was never closed", "INFO next"])
    assert len(out) == 1 and out[0].errortype == "SyntaxError"


def test_exception_group_sub_blocks_stay_in_entry():
    out = _run([*TB[:3], "ExceptionGroup: two (2 sub-exceptions)", "  +-+---- 1 ----", "    | ValueError: a", "INFO next"])
    assert len(out) == 1 and "ValueError: a" in out[0].message


def test_pending_lines_resume_across_feeds():
    t2 = T.replace(second=5)
    a = LineAssembler()
    out = []
    for ln in TB[:2]:
        out += a.feed(T, ln)
    assert out == [] and a.pending() == [(T, TB[0]), (T, TB[1])] and a.in_frames()
    b = LineAssembler()  # 다음 폴링: 넘겨받은 줄을 먼저 다시 넣는다
    for ts, ln in a.pending():
        out += b.feed(ts, ln)
    for ln in TB[2:]:
        out += b.feed(t2, ln)
    assert out == [] and not b.in_frames()  # 예외 줄까지 읽었지만 체인이 이어질 수 있다
    out += b.feed(t2, "INFO next")
    assert len(out) == 1 and out[0].ts == T and out[0].errortype == "ValueError"
    assert b.pending() == []


def test_pending_includes_held_error_header():
    a = LineAssembler()
    assert a.feed(T, "ERROR:    Exception in ASGI application") == []
    assert a.pending() == [(T, "ERROR:    Exception in ASGI application")]
    assert not a.in_frames()
    assert [e.message for e in a.flush()] == ["ERROR:    Exception in ASGI application"]
