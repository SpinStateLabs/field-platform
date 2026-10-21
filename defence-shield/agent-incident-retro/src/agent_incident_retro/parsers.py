"""Log parsers. Read-only: inputs are opened ``rb`` and never written.

Line identity is the contract the evidence pack depends on: a file is split
on ``\\n``, a trailing ``\\r`` is stripped, and each line's sha-256 is taken
over those exact bytes. ``split_lines`` is the ONE implementation used by both
``scan`` and ``verify --sources``, so the two cannot disagree.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import unquote

from .models import InputFile, LineRef, Request
from .signatures import classify

LineParser = Callable[[str], "Parsed | None"]


def never_fatal(parse: LineParser) -> LineParser:
    """SPEC §3.1: an unparseable line is counted, never fatal. The stdlib raises
    more than ValueError on hostile input (OverflowError on a year-9999
    timestamp with an offset, RecursionError on 100 000 nested brackets,
    ValueError-not-JSONDecodeError on a 5000-digit integer, OverflowError on
    ``1e400``), so every parser is wrapped here: any Exception from one line
    means that line is unparsed. BaseException (KeyboardInterrupt, SystemExit,
    and the no-network tripwire in the tests) still propagates."""

    @functools.wraps(parse)
    def guarded(text: str) -> Parsed | None:
        try:
            return parse(text)
        except Exception:
            return None

    return guarded

# ----------------------------------------------------------- line identity


def split_lines(data: bytes) -> Iterator[tuple[int, bytes]]:
    """Yield (1-based line number, line bytes) for every line of ``data``.

    A final empty segment after a trailing newline is not a line. Empty lines
    in the middle keep their numbers (so citations stay addressable) but are
    yielded too; callers skip them.
    """
    parts = data.split(b"\n")
    if parts and parts[-1] == b"":
        parts.pop()
    for number, line in enumerate(parts, start=1):
        if line.endswith(b"\r"):
            line = line[:-1]
        yield number, line


def line_sha256(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------- CLF parser

_Q = r'"((?:[^"\\]|\\.)*)"'
CLF = re.compile(
    r"^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "
    + _Q.replace("(", "(?P<req>", 1)
    + r" (?P<status>\d{3}) (?P<size>\S+)"
    + r"(?: " + _Q.replace("(", "(?P<ref>", 1) + r" " + _Q.replace("(", "(?P<ua>", 1) + r")?"
)


def _unescape(value: str | None) -> str:
    if not value:
        return ""
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _split_target(target: str) -> tuple[str, str]:
    path, _, query = target.partition("?")
    return unquote(path), query


def _split_request_line(req: str) -> tuple[str, str] | None:
    parts = req.split(" ")
    if len(parts) < 2 or not parts[0] or parts[0] == "-":
        return None
    if len(parts) >= 3 and parts[-1].upper().startswith("HTTP/"):
        return parts[0], " ".join(parts[1:-1])
    return parts[0], " ".join(parts[1:])


@dataclass
class Parsed:
    ts: datetime
    client_ip: str
    method: str
    target: str
    status: int
    user_agent: str
    referer: str


@never_fatal
def parse_clf(text: str) -> Parsed | None:
    m = CLF.match(text)
    if not m:
        return None
    request = _split_request_line(_unescape(m.group("req")))
    if request is None:
        return None
    try:
        ts = datetime.strptime(m.group("ts"), "%d/%b/%Y:%H:%M:%S %z").astimezone(timezone.utc)
    except ValueError:
        return None
    ua = _unescape(m.group("ua"))
    ref = _unescape(m.group("ref"))
    return Parsed(
        ts=ts,
        client_ip=m.group("ip"),
        method=request[0],
        target=request[1],
        status=int(m.group("status")),
        user_agent="" if ua == "-" else ua,
        referer="" if ref == "-" else ref,
    )


# ----------------------------------------------------------- JSONL parser

#: canonical field -> candidate keys (dotted paths allowed), first hit wins.
PRESETS: dict[str, dict[str, list[str]]] = {
    "generic": {
        "ts": ["timestamp", "time", "ts", "@timestamp"],
        "ip": ["client_ip", "ip", "remote_addr", "clientIp"],
        "method": ["method", "request_method", "http.method"],
        "uri": ["uri", "url", "request_uri", "path", "http.uri"],
        "status": ["status", "status_code", "http.status"],
        "ua": ["user_agent", "ua", "http_user_agent", "http.user_agent"],
        "referer": ["referer", "referrer", "http_referer"],
    },
    # Cloudflare Logpush HTTP-requests dataset field names. Verify against the
    # customer's job: the timestamp format (RFC 3339 / unix / unixnano) is a
    # job option, and every format is accepted here.
    "cloudflare": {
        "ts": ["EdgeStartTimestamp"],
        "ip": ["ClientIP"],
        "method": ["ClientRequestMethod"],
        "uri": ["ClientRequestURI"],
        "status": ["EdgeResponseStatus"],
        "ua": ["ClientRequestUserAgent"],
        "referer": ["ClientRequestReferer"],
    },
}


def _dig(record: dict[str, Any], dotted: str) -> Any:
    node: Any = record
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _pick(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = _dig(record, key)
        if value is not None and value != "":
            return value
    return None


def _to_utc(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e17:
            v /= 1e9  # nanoseconds
        elif v > 1e14:
            v /= 1e6  # microseconds
        elif v > 1e11:
            v /= 1e3  # milliseconds
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d+(\.\d+)?", text):
            return _to_utc(float(text))
        try:
            ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    return None


def make_jsonl_parser(field_map: dict[str, list[str]]) -> LineParser:
    missing = {"ts", "ip", "uri", "status"} - set(field_map)
    if missing:
        raise ValueError(f"field map lacks required fields: {sorted(missing)}")

    @never_fatal
    def parse(text: str) -> Parsed | None:
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(record, dict):
            return None
        ts = _to_utc(_pick(record, field_map["ts"]))
        ip = _pick(record, field_map["ip"])
        uri = _pick(record, field_map["uri"])
        status = _pick(record, field_map["status"])
        if ts is None or ip is None or uri is None or status is None:
            return None
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            return None
        method = _pick(record, field_map.get("method", [])) or "GET"
        ua = _pick(record, field_map.get("ua", [])) or ""
        ref = _pick(record, field_map.get("referer", [])) or ""
        target = str(uri)
        if "://" in target:  # full URL: keep path + query
            target = "/" + target.split("://", 1)[1].partition("/")[2]
        # JSON strings may hold lone surrogates (\udXXX); drop them so a later
        # utf-8 encode (hashing, canonical pack) cannot raise on one bad line.
        clean = lambda s: str(s).encode("utf-8", "replace").decode("utf-8")
        return Parsed(ts, clean(ip), clean(method), clean(target), status_int, clean(ua), clean(ref))

    return parse


# ----------------------------------------------------------------- driver


def resolve_parser(fmt: str, preset: str = "generic", overrides: dict[str, str] | None = None) -> LineParser:
    if fmt == "clf":
        return parse_clf
    if fmt == "jsonl":
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}; known: {sorted(PRESETS)}")
        field_map = {k: list(v) for k, v in PRESETS[preset].items()}
        for key, path in (overrides or {}).items():
            field_map[key] = [path]
        return make_jsonl_parser(field_map)
    raise ValueError(f"unknown format {fmt!r}; known: clf, jsonl")


def unique_labels(paths: list[Path]) -> list[str]:
    seen: dict[str, int] = {}
    labels: list[str] = []
    for path in paths:
        base = path.name
        seen[base] = seen.get(base, 0) + 1
        labels.append(base if seen[base] == 1 else f"{base}#{seen[base]}")
    return labels


def read_input(path: Path, label: str, fmt: str, parser: LineParser) -> tuple[InputFile, list[Request]]:
    data = path.read_bytes()  # read-only: never opened for writing
    requests: list[Request] = []
    total = parsed = unparsed = 0
    for number, line in split_lines(data):
        if not line.strip():
            continue
        total += 1
        text = line.decode("utf-8", errors="replace")
        p = parser(text)
        if p is None:
            unparsed += 1
            continue
        parsed += 1
        path_part, query = _split_target(p.target)
        families, fps = classify(path_part, query)
        requests.append(
            Request(
                ref=LineRef(input=label, line=number, sha256=line_sha256(line)),
                ts=p.ts,
                client_ip=p.client_ip,
                method=p.method,
                path=path_part,
                query=query,
                status=p.status,
                user_agent=p.user_agent,
                referer=p.referer,
                raw=text,
                families=families,
                fingerprints=fps,
            )
        )
    info = InputFile(
        label=label,
        sha256=file_sha256(data),
        bytes=len(data),
        lines=total,
        parsed=parsed,
        unparsed=unparsed,
        format=fmt,
    )
    return info, requests
