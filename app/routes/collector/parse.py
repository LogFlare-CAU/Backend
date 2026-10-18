import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime

_SECRET_KV = re.compile(r"(?i)([\w-]*(?:token|key|password|passwd|pwd|secret)\w*[\"']?\s*[=:]\s*[\"']?)([^\s&\"',}]+)")
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
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "<hex>"),
    (re.compile(r"\b\d+(?:\.\d+)?\b"), "<n>"),
]


def normalize(message: str) -> str:
    lines = [ln for ln in message.splitlines() if ln.strip()]
    if not lines:
        return ""
    line = lines[-1] if "Traceback (most recent call last):" in message else lines[0]
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
_ACCESS_RX = re.compile(r'HTTP/1\.[01]" \d{3}')
_EXC_LINE = re.compile(r"^([\w.]+)(?::|$)")
_CHAIN = ("During handling of the above exception", "The above exception was the direct cause")
_TB_START = "Traceback (most recent call last):"


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
    """줄을 하나씩 받아 Entry 로 묶는다. 트레이스백(체인 포함)은 한 Entry."""

    def __init__(self) -> None:
        self._buf: list[str] = []
        self._ts: datetime | None = None
        self._done = False  # 예외 줄까지 읽음 — 체인이 이어지는지 다음 줄로 판단

    def _emit(self) -> list[Entry]:
        buf, ts, self._buf, self._ts, self._done = self._buf, self._ts, [], None, False
        while buf and not buf[-1].strip():
            buf.pop()
        if not buf or ts is None:
            return []
        m = _EXC_LINE.match(buf[-1])
        etype = m.group(1).rsplit(".", 1)[-1] if m else None
        return [Entry("ERROR", etype, "\n".join(buf), ts)]

    def feed(self, ts: datetime, line: str) -> list[Entry]:
        line = line.rstrip("\r\n")
        out: list[Entry] = []
        if self._buf:
            blank = not line.strip()
            if self._done:
                if blank:
                    self._buf.append(line)
                    return []
                if line.startswith(_CHAIN):
                    self._buf.append(line)
                    self._done = False
                    return []
                out = self._emit()
            elif blank or line[0] in " \t" or line.strip() == _TB_START:
                self._buf.append(line)
                return []
            else:  # 프레임 뒤 첫 비들여쓰기 줄 = 예외 줄
                self._buf.append(line)
                self._done = True
                return []
        if line.strip() == _TB_START:
            self._buf, self._ts = [line], ts
            return out
        c = classify(line)
        if c:
            out.append(Entry(c[0], c[1], line, ts))
        return out

    def flush(self) -> list[Entry]:
        return self._emit()
