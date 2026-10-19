import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime

# (?<![\w-]) : 단어 중간에서 다시 시작하지 않게 — 없으면 긴 단어에서 O(n^2) 백트래킹
_SECRET_KV = re.compile(r"(?i)((?<![\w-])[\w-]*(?:(?<![A-Za-z])(?:token|key|password|passwd|pwd|secret)|(?-i:(?<=[a-z])(?:Token|Key|Password|Passwd|Pwd|Secret)))[\"']?\s*[=:]\s*[\"']?)([^\s&\"',}]+)")
_BEARER = re.compile(r"(?i)\b(Bearer\s+)\S+")
_URL_USER = re.compile(r"(://)[^/\s:@]+:[^/\s@]+@")


def mask_secrets(text: str) -> str:
    text = _URL_USER.sub(r"\1***@", text)
    text = _BEARER.sub(r"\1***", text)
    return _SECRET_KV.sub(r"\1***", text)


_NORMALIZERS = [
    (re.compile(r"\"[^\"]*\"|'[^']*'"), "<str>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "<hex>"),
    (re.compile(r"\b\d+(?:\.\d+)?\b"), "<n>"),
]


def headline(message: str) -> str:
    """사람이 볼 대표 줄. 트레이스백이면 마지막 예외 줄, 아니면 첫 줄."""
    lines = [ln for ln in message.splitlines() if ln.strip()]
    if not lines:
        return ""
    if _TB_START in message or _FRAME.match(lines[0]):
        return (_exc_line(lines) or lines[-1]).strip()
    return lines[0].strip()


def normalize(message: str) -> str:
    line = headline(message)
    for rx, repl in _NORMALIZERS:
        line = rx.sub(repl, line)
    return line.strip()


def fingerprint(source: str, level: str, message: str) -> str:
    return hashlib.sha1(f"{source}|{level}|{normalize(message)}".encode()).hexdigest()[:16]


@dataclass
class Entry:
    level: str
    errortype: str | None
    message: str
    ts: datetime


_JSON_LEVELS = {
    "error": "ERROR", "critical": "CRITICAL", "fatal": "CRITICAL", "panic": "CRITICAL",
    "warn": "WARNING", "warning": "WARNING",
}
_ERR_RX = re.compile(r"\b(CRITICAL|FATAL|ERROR|Traceback|Exception|panic)\b", re.I)
_WARN_RX = re.compile(r"\b(WARNING|WARN)\b", re.I)
_ACCESS_RX = re.compile(r'HTTP/(?:1\.[01]|2(?:\.0)?|3)" \d{3}')
_EXC_LINE = re.compile(r"^([\w.]+)(?::|$)")
_LEVEL_WORDS = {"TRACE", "DEBUG", "INFO", "NOTICE", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"}
_FRAME = re.compile(r'^\s+File "')
_CHAIN = ("During handling of the above exception", "The above exception was the direct cause")
_TB_START = "Traceback (most recent call last):"


def _is_exc_line(line: str) -> bool:
    """프레임 뒤 비들여쓰기 줄이 예외 줄처럼 생겼는지. 로그 줄(INFO: …, 시각으로 시작)은 아니다."""
    m = _EXC_LINE.match(line)
    return bool(m) and m.group(1).upper() not in _LEVEL_WORDS


def _exc_line(lines: list[str]) -> str | None:
    """마지막 비들여쓰기 줄이 예외 줄이면 그 줄 (ExceptionGroup 의 하위 블록은 들여쓰기라 건너뛴다)."""
    for ln in reversed(lines):
        if not ln.strip() or ln[:1] in " \t":
            continue
        if ln.strip() == _TB_START or ln.startswith(_CHAIN) or not _is_exc_line(ln):
            return None
        return ln
    return None


def classify(line: str) -> tuple[str, str | None] | None:
    s = line.strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            if obj.get("logger") == "http.log.access":
                return None
            level = _JSON_LEVELS.get(str(obj.get("level", "")).lower())
            return (level, None) if level else None
    if _ACCESS_RX.search(line):
        return None
    m = _ERR_RX.search(line)
    if m:
        return ("CRITICAL" if m.group(1).upper() in ("CRITICAL", "FATAL") else "ERROR", None)
    if _WARN_RX.search(line):
        return ("WARNING", None)
    return None


class LineAssembler:
    """줄을 하나씩 받아 Entry 로 묶는다.

    - 트레이스백(체인·ExceptionGroup 포함)은 한 Entry.
    - 바로 뒤에 트레이스백이 오는 ERROR 줄(logger.exception)은 그 트레이스백의 머리로 합친다.
    - 아직 끝나지 않은 줄은 pending() 으로 꺼내 다음 폴링의 새 assembler 에 먼저 넣으면 이어진다.
    """

    def __init__(self) -> None:
        self._head: tuple[datetime, str, str] | None = None  # 트레이스백이 이어지는지 기다리는 ERROR 줄
        self._buf: list[tuple[datetime, str]] = []
        self._level = "ERROR"
        self._bare = False  # Traceback 머리 없이 File 줄로 시작 (스크립트 SyntaxError)
        self._done = False  # 예외 줄까지 읽음 — 체인이 이어지는지 다음 줄로 판단

    def pending(self) -> list[tuple[datetime, str]]:
        head = [(self._head[0], self._head[1])] if self._head else []
        return head + list(self._buf)

    def in_frames(self) -> bool:
        """예외 줄을 아직 못 읽은 트레이스백 중간."""
        return bool(self._buf) and not self._done

    def _emit_head(self) -> list[Entry]:
        if self._head is None:
            return []
        ts, line, level = self._head
        self._head = None
        return [Entry(level, None, line, ts)]

    def _emit(self) -> list[Entry]:
        buf, level, bare = self._buf, self._level, self._bare
        self._buf, self._level, self._bare, self._done = [], "ERROR", False, False
        while buf and not buf[-1][1].strip():
            buf.pop()
        if not buf:
            return []
        lines = [ln for _, ln in buf]
        exc = _exc_line(lines)
        if bare and exc is None:
            return []  # 예외 줄 없는 File 줄 묶음(print_stack 등)은 에러가 아니다
        etype = _EXC_LINE.match(exc).group(1).rsplit(".", 1)[-1] if exc else None
        return [Entry(level, etype, "\n".join(lines), buf[0][0])]

    def feed(self, ts: datetime, line: str) -> list[Entry]:
        line = line.rstrip("\r\n")
        out: list[Entry] = []
        if self._buf:
            blank = not line.strip()
            if self._done:
                if blank or line[0] in " \t":  # 빈 줄, ExceptionGroup 하위 블록
                    self._buf.append((ts, line))
                    return []
                if line.startswith(_CHAIN):
                    self._buf.append((ts, line))
                    self._done = False
                    return []
                out = self._emit()
            elif blank or line[0] in " \t" or line.strip() == _TB_START:
                self._buf.append((ts, line))
                return []
            elif _is_exc_line(line):  # 프레임 뒤 첫 비들여쓰기 줄 = 예외 줄
                self._buf.append((ts, line))
                self._done = True
                return []
            else:  # 잘린 트레이스백 — 이 줄은 아래에서 새로 판정한다
                out = self._emit()
        if line.strip() == _TB_START:
            if self._head is not None:
                hts, hline, hlevel = self._head
                self._head = None
                self._buf, self._level = [(hts, hline), (ts, line)], hlevel
            else:
                self._buf = [(ts, line)]
            return out
        out += self._emit_head()
        if _FRAME.match(line):
            self._buf, self._bare = [(ts, line)], True
            return out
        c = classify(line)
        if c and c[0] != "WARNING":
            self._head = (ts, line, c[0])
        elif c:
            out.append(Entry(c[0], c[1], line, ts))
        return out

    def flush(self) -> list[Entry]:
        return self._emit() + self._emit_head()
