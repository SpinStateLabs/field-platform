#!/usr/bin/env python3
"""estate_kill_watcher - carry an estate kill to a Claude Code session governed by a FIELD manifest.

Standard library only (PyYAML only when --manifest is used). ASCII output. Harness ADR-0072.

    estate_kill_watcher.py --agent ID --base URL (--sentinel PATH | --manifest PATH)
        [--interval 10] [--max-age-s N] [--kill-prefix /killswitch]
        [--secret-file PATH] [--timeout 5] [--once]

WHY. The Claude Code Enforcement Gate (Force-Field `field` plugin, E1) denies every gated tool call while
a sentinel file exists. A manifest whose kill switch is the estate service got only the default local file,
so an estate kill (`POST /kill/{agent_id}`) did not stop a governed session. The gate makes no network call
(per-call latency, and an outage would halt or free every session). This tool is the network side: it polls
`GET /heartbeat/{agent_id}` and keeps ONE local file in step with it.

WHAT IT DOES, per poll (each step is pinned by tools/tests/test_estate_kill_watcher.py):
1. GET {base}{kill-prefix}/heartbeat/{agent}. A read: a poll is not a check-in and writes nothing on the estate.
   The answer is trusted only when it is HTTP 200, a JSON object naming the same agent_id, with a boolean
   `killed`. Anything else (transport error, 4xx/5xx, redirect, malformed body, wrong agent) is "no answer".
2. killed=true  -> create the sentinel (atomic), unless it already exists.
   killed=false -> remove the sentinel, but ONLY a file this tool wrote (first line is MARKER). A sentinel a
                   human created is left in place: a revive on the estate does not undo a human's halt.
   no answer    -> change nothing. The sentinel stays as it was (a kill is never dropped by an outage).
3. After a successful poll only, refresh the liveness stamp `<sentinel>.alive` (atomic). A gate whose manifest
   sets kill_switch.sentinel_max_age_s denies when that stamp is missing, older than the limit, or in the
   future, so a watcher that is down, or an estate that has been unreachable for the whole window, halts the
   session instead of silently dropping a kill. The limit must exceed twice the poll interval (else refused).

The sentinel and stamp path must be the manifest's kill_switch.local_sentinel (--manifest reads it and refuses a
--sentinel that disagrees, which is the whole point of the key). Relative paths resolve against the manifest's
directory, as the gate resolves them against the project root.

It never writes to the estate (no ledger append, no kill, no revive) and never prints the shared secret.
x-field-auth comes from FIELD_SHARED_SECRET or --secret-file. Redirects are never followed and no environment
proxy is used (the secret must not travel). It does NOT sign requests as a caller: GET /heartbeat needs only
x-field-auth on the services in this repo; if an estate starts requiring caller signatures on it, this tool
needs extending (not verified against a GB10 with A7b).

EXIT CODES. --once: 0 the answer was applied; 3 no answer (nothing changed); 2 refused (usage, path, manifest).
Loop mode runs until interrupted; poll failures are logged, never fatal; only a refusal exits (2).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request

MARKER = "field-estate-kill-watcher v1"
STAMP_SUFFIX = ".alive"
AGENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
HTTP_TIMEOUT = 5.0
EXIT_OK, EXIT_REFUSED, EXIT_NO_ANSWER = 0, 2, 3


class Refused(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a 3xx is an answer, never a hop: the secret must not travel


_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))


def log(msg: str) -> None:
    print(f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}", flush=True)


def read_secret(secret_file: str | None) -> str | None:
    if secret_file:
        try:
            with open(secret_file, encoding="utf-8") as fh:
                value = fh.read().strip()
        except (OSError, UnicodeDecodeError):
            raise Refused("--secret-file is not readable")
        if not value:
            raise Refused("--secret-file is empty")
    else:
        value = os.environ.get("FIELD_SHARED_SECRET", "")
    if value and (not value.isascii() or not value.isprintable() or any(c.isspace() for c in value)):
        raise Refused("shared secret contains whitespace, control or non-ASCII characters (value not shown)")
    return value or None


def poll(base: str, prefix: str, agent: str, secret: str | None, timeout: float) -> tuple[bool | None, str]:
    """(killed, status) from the estate, or (None, reason). The reason never carries a body or the secret."""
    url = f"{base.rstrip('/')}{prefix}/heartbeat/{agent}"
    headers = {"Accept": "application/json"}
    if secret:
        headers["x-field-auth"] = secret
    try:
        with _OPENER.open(urllib.request.Request(url, headers=headers, method="GET"), timeout=timeout) as resp:
            status, raw = resp.status, resp.read(65536)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # the type name only: a message can carry the URL or the secret
        return None, f"transport error {type(exc).__name__}"
    if status != 200:
        return None, f"HTTP {status}"
    try:
        body = json.loads(raw)
    except ValueError:
        return None, "answer is not JSON"
    if not isinstance(body, dict) or body.get("agent_id") != agent or not isinstance(body.get("killed"), bool):
        return None, "answer is not a heartbeat for this agent"
    return body["killed"], str(body.get("status", ""))[:40]


def _write_atomic(path: str, text: str) -> None:
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.tmp-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _owned(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.readline().strip() == MARKER
    except (OSError, UnicodeDecodeError):
        return False


def apply(sentinel: str, killed: bool, agent: str, status: str) -> str:
    """Bring the sentinel in step with the estate. Returns what happened, for the log."""
    exists = os.path.lexists(sentinel)
    if exists and (os.path.islink(sentinel) or not os.path.isfile(sentinel)):
        raise Refused("sentinel path exists and is not a regular file; left alone")
    if killed:
        if exists:
            return "killed: sentinel already present"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        _write_atomic(sentinel, f"{MARKER}\n{json.dumps({'agent_id': agent, 'status': status, 'created_at': now})}\n")
        return "killed: sentinel created"
    if not exists:
        return "alive: no sentinel"
    if _owned(sentinel):
        os.unlink(sentinel)
        return "alive: sentinel removed (revive)"
    return "alive: sentinel is not the watcher's, left in place"


def stamp(sentinel: str) -> None:
    _write_atomic(sentinel + STAMP_SUFFIX, datetime.datetime.now(datetime.timezone.utc).isoformat() + "\n")


def from_manifest(path: str) -> tuple[str, int | None]:
    try:
        import yaml
    except ImportError:
        raise Refused("--manifest needs PyYAML (pip install pyyaml); or pass --sentinel and --max-age-s")
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        raise Refused("--manifest is not readable YAML")
    ks = ((data or {}).get("enforcement") or {}).get("kill_switch") if isinstance(data, dict) else None
    raw = ks.get("local_sentinel") if isinstance(ks, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        raise Refused("the manifest sets no enforcement.kill_switch.local_sentinel")
    raw = raw.strip()
    if raw.lower().startswith("file://"):
        raw = raw[len("file://"):]
    p = os.path.expanduser(raw)
    if not os.path.isabs(p):
        p = os.path.join(os.path.dirname(os.path.abspath(path)), p)
    age = ks.get("sentinel_max_age_s")
    if age is not None and (isinstance(age, bool) or not isinstance(age, int) or age < 1):
        raise Refused("the manifest's sentinel_max_age_s is not an integer of 1 or more")
    return os.path.abspath(p), age


def settle(args) -> tuple[str, int | None]:
    sentinel, age = None, args.max_age_s
    if args.manifest:
        sentinel, m_age = from_manifest(args.manifest)
        if args.sentinel and os.path.abspath(os.path.expanduser(args.sentinel)) != sentinel:
            raise Refused("--sentinel disagrees with the manifest's kill_switch.local_sentinel")
        if args.max_age_s is not None and m_age is not None and args.max_age_s != m_age:
            raise Refused("--max-age-s disagrees with the manifest's sentinel_max_age_s")
        age = m_age if m_age is not None else args.max_age_s
    elif args.sentinel:
        sentinel = os.path.abspath(os.path.expanduser(args.sentinel))
    else:
        raise Refused("give --sentinel or --manifest")
    if not AGENT_RE.match(args.agent):
        raise Refused("--agent must be 1-128 characters of letters, digits, '.', '_' or '-'")
    if not args.base.lower().startswith(("http://", "https://")):
        raise Refused("--base must be an http(s) URL")
    if not args.kill_prefix.startswith("/") or args.kill_prefix.endswith("/") and args.kill_prefix != "/":
        raise Refused("--kill-prefix must start with '/' and not end with one (use '' via --kill-prefix /)")
    if args.interval <= 0:
        raise Refused("--interval must be positive")
    if age is not None and age <= 2 * args.interval:
        raise Refused(f"sentinel_max_age_s ({age}) must exceed twice --interval ({args.interval:g}): "
                      "the gate would deny between two healthy polls")
    return sentinel, age


def run_once(args, sentinel: str, secret: str | None) -> int:
    prefix = "" if args.kill_prefix == "/" else args.kill_prefix
    killed, info = poll(args.base, prefix, args.agent, secret, args.timeout)
    if killed is None:
        log(f"no answer from the estate ({info}); sentinel and stamp left as they were")
        return EXIT_NO_ANSWER
    try:
        what = apply(sentinel, killed, args.agent, info)
    except Refused as exc:
        log(f"refused: {exc}")
        return EXIT_REFUSED
    try:
        stamp(sentinel)
    except OSError as exc:
        log(f"could not write the liveness stamp ({type(exc).__name__})")
        return EXIT_NO_ANSWER
    log(f"{what} (estate status {info or 'unknown'})")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Carry an estate kill to a governed Claude Code session.")
    ap.add_argument("--agent", required=True, help="the agent id registered in the estate")
    ap.add_argument("--base", required=True, help="estate proxy URL, e.g. http://10.0.0.62:18080")
    ap.add_argument("--sentinel", help="the manifest's kill_switch.local_sentinel (absolute, or relative to the cwd)")
    ap.add_argument("--manifest", help="read kill_switch.local_sentinel / sentinel_max_age_s from this manifest")
    ap.add_argument("--max-age-s", type=int, default=None, help="the manifest's sentinel_max_age_s, to check the interval")
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--kill-prefix", default="/killswitch", help="proxy prefix of the kill-switch service")
    ap.add_argument("--secret-file")
    ap.add_argument("--timeout", type=float, default=HTTP_TIMEOUT)
    ap.add_argument("--once", action="store_true", help="poll once and exit")
    args = ap.parse_args(argv)
    try:
        sentinel, _age = settle(args)
        secret = read_secret(args.secret_file)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if args.once:
        return run_once(args, sentinel, secret)
    log(f"watching agent {args.agent}; sentinel {os.path.basename(sentinel)}; every {args.interval:g} s")
    try:
        while True:
            code = run_once(args, sentinel, secret)
            if code == EXIT_REFUSED:
                return code
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
