"""The X3 canary agent: a real agent-side halt endpoint (v1.2 X3, arming step A6).

A long-running process that does no business work. It runs as the GB10
compose service ``canary-agent`` (profile ``x3``) under the gate-verification
identity ``canary-gb10``, whose manifest declares
``enforcement.kill_switch.endpoint: http://canary-agent:8090/halt``. With
``FIELD_KILL_ENDPOINT_ALLOWLIST=canary-agent`` on the kill-switch (A6), a kill
of ``canary-gb10`` really calls this process.

Routes (stdlib ``http.server``; no framework, no field authn):

* ``POST /halt`` — requires ``x-field-kill-origin: kill-switch`` (403
  otherwise, and nothing changes). Stops the work loop and answers 200 with
  the nonce parsed from the kill reason (``x3-<nonce>``, carried by the
  kill-switch in ``x-field-kill-reason``, percent-encoded; a JSON body
  ``{"reason": ...}`` is read when the header is absent). The process NEVER
  exits on a halt: it keeps serving ``/status`` so the halt can be observed.
* ``GET /status`` — ``{halted, nonce, since, ...}``.
* ``GET /health`` — ``{ok, service, build_sha}`` (open, like every service).

ENFORCED (tests/test_canary_agent.py): the origin header is required; a halt
stops the work loop before the 200 is written (a tick and a halt take the same
lock, so no unit of work starts after it); the process is still running and
serving after a halt; ``/status`` reflects the latest halt's nonce and the
FIRST halt's time. A halt is sticky for the life of the process: a kill-switch
``/revive`` flips the registry, not this process — a restart resumes it.

DECLARED only: the origin header is a marker, NOT authentication. Anything
that can reach ``canary-agent:8090`` can halt the canary (the service has no
published port, so on the GB10 that is the compose network). This is the
canary's endpoint; no business agent's in-flight process is made to stop by it.

Heartbeat polling (``FIELD_CANARY_HEARTBEAT_EVERY`` seconds, 0 = OFF, the
default): a read-only ``GET /heartbeat/{agent}`` (never a check-in, so it
cannot move ``/liveness`` under a probe) that halts on ``killed: true`` and,
per the SDK's fail-closed contract, on an unreachable kill-switch. The X3 live
check runs with it OFF, so the halt it observes came from the endpoint.

``python -m field_agent.canary x3-check`` is that live check (run inside the
kill-switch container, which holds the service URLs and the perimeter
secret): kill with reason ``x3-<nonce>`` => ``endpoint_result.outcome ==
"called"`` AND ``/status`` halted with the same nonce; revive => exactly +1
``kill.revive``; drill on the ``canary``-domain record =>
``endpoint_confirmed_ms`` present. Exit 0 only when every check passes; 2 when
it refuses to act (not a canary).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import signal
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

ORIGIN_HEADER = "x-field-kill-origin"
ORIGIN_VALUE = "kill-switch"
REASON_HEADER = "x-field-kill-reason"
DEFAULT_PORT = 8090
#: A JSON body larger than this is not read (the reason header is the path the
#: kill-switch uses; the body is a manual convenience).
MAX_BODY_BYTES = 64 * 1024
#: ``x3-<nonce>`` anywhere in the reason, bounded on both sides.
_NONCE = re.compile(r"(?<![A-Za-z0-9_-])x3-([A-Za-z0-9_-]{1,128})(?![A-Za-z0-9_-])")

CANARIES = frozenset({"canary-gb10", "canary-fly"})
CANARY_DOMAIN = "canary"


def parse_nonce(reason: str | None) -> str | None:
    """``'x3-4f2a'`` -> ``'4f2a'``; no ``x3-`` token -> None."""
    if not reason:
        return None
    match = _NONCE.search(reason)
    return match.group(1) if match else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CanaryState:
    """Everything ``/status`` reports. One lock guards the halt flag AND the
    work tick, so a unit of work either completed before a halt or never
    starts after it."""

    def __init__(self, agent_id: str, heartbeat_every: float = 0.0):
        self._lock = threading.Lock()
        self.agent_id = agent_id
        self.heartbeat_every = heartbeat_every
        self.started_at = _now()
        self.halted = False
        self.nonce: str | None = None
        self.since: str | None = None
        self.last_halt_at: str | None = None
        self.last_halted_by: str | None = None
        self.halts = 0
        self.work_ticks = 0

    def tick(self) -> bool:
        """One unit of (no-op) work. False, and nothing done, once halted."""
        with self._lock:
            if self.halted:
                return False
            self.work_ticks += 1
            return True

    def halt(self, *, source: str, nonce: str | None = None, set_nonce: bool = False) -> dict:
        with self._lock:
            now = _now()
            if not self.halted:
                self.halted = True
                self.since = now
            if set_nonce:
                # The endpoint's LATEST signal names the nonce (None when its
                # reason carried none): a stale nonce can never satisfy a check
                # for a fresh one. A heartbeat halt carries no reason and
                # leaves the nonce alone.
                self.nonce = nonce
            self.halts += 1
            self.last_halt_at = now
            self.last_halted_by = source
            return self._snapshot()

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "halted": self.halted,
            "nonce": self.nonce,
            "since": self.since,
            "halts": self.halts,
            "last_halt_at": self.last_halt_at,
            "last_halted_by": self.last_halted_by,
            "work_ticks": self.work_ticks,
            "heartbeat_every": self.heartbeat_every,
            "started_at": self.started_at,
            "pid": os.getpid(),
        }


def _handler_for(state: CanaryState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "field-canary-agent"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # one line, no headers
            command, path = getattr(self, "command", None), str(getattr(self, "path", "")).split("?")[0]
            code = args[1] if fmt.startswith('"%s"') and len(args) > 1 else ""
            try:
                sys.stdout.write(f"canary-agent {command} {path} {code}\n")
                sys.stdout.flush()
            except Exception:  # a closed stdout never takes a request down
                pass

        def _send(self, status: int, body: dict) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _drain(self) -> bytes:
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True  # never left half-read on a kept-alive socket
                return b""
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                return b""
            if length > MAX_BODY_BYTES:
                self.close_connection = True
                return b""
            return self.rfile.read(length)

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path == "/status":
                self._send(200, state.snapshot())
            elif path == "/health":
                from field_core.buildinfo import build_sha

                self._send(200, {"ok": True, "service": "canary-agent",
                                 "agent_id": state.agent_id, "build_sha": build_sha()})
            elif path == "/halt":
                self._send(405, {"error": "POST /halt"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            path = self.path.split("?")[0]
            body = self._drain()
            if path != "/halt":
                self._send(404 if path not in ("/status", "/health") else 405, {"error": "not found"})
                return
            if (self.headers.get(ORIGIN_HEADER) or "").strip() != ORIGIN_VALUE:
                self._send(403, {"error": f"{ORIGIN_HEADER}: {ORIGIN_VALUE} required", "halted": state.snapshot()["halted"]})
                return
            reason: str | None = None
            raw_reason = self.headers.get(REASON_HEADER)
            if raw_reason:
                reason = urllib.parse.unquote(raw_reason)
            elif body:
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict) and isinstance(parsed.get("reason"), str):
                        reason = parsed["reason"]
                except ValueError:
                    reason = None
            snap = state.halt(source="endpoint", nonce=parse_nonce(reason), set_nonce=True)
            self._send(200, {"halted": snap["halted"], "nonce": snap["nonce"], "since": snap["since"],
                             "agent_id": snap["agent_id"], "halts": snap["halts"]})

    return Handler


class CanaryAgent:
    """The server, the work loop and the optional heartbeat poller."""

    def __init__(self, agent_id: str, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 work_every: float = 5.0, heartbeat_every: float = 0.0,
                 liveness: Any | None = None):
        self.state = CanaryState(agent_id, heartbeat_every=heartbeat_every)
        self.work_every = work_every
        self.heartbeat_every = heartbeat_every
        self._liveness = liveness
        self._stop = threading.Event()
        self.server = ThreadingHTTPServer((host, port), _handler_for(self.state))
        self.server.daemon_threads = True
        self._threads: list[threading.Thread] = []
        self._serving = False

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def _work_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.state.tick()
            except Exception:  # pragma: no cover - a tick is a counter; never die on it
                pass
            self._stop.wait(self.work_every)

    def poll_heartbeat_once(self) -> None:
        """Read-only poll. killed => halt; unreachable => halt (fail closed)."""
        if self._liveness is None:
            from field_agent.liveness import LivenessClient

            self._liveness = LivenessClient()
        try:
            hb = self._liveness.heartbeat(self.state.agent_id)
        except Exception:
            self.state.halt(source="heartbeat_unreachable")
            return
        if getattr(hb, "killed", True):
            self.state.halt(source="heartbeat")

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_heartbeat_once()
            except Exception:  # pragma: no cover - poll_heartbeat_once never raises
                pass
            self._stop.wait(self.heartbeat_every)

    def start_background(self) -> None:
        self._threads.append(threading.Thread(target=self._work_loop, name="canary-work", daemon=True))
        if self.heartbeat_every > 0:
            self._threads.append(threading.Thread(target=self._heartbeat_loop, name="canary-heartbeat", daemon=True))
        for t in self._threads:
            t.start()

    def serve_forever(self) -> None:
        self.start_background()
        self._serving = True
        self.server.serve_forever()

    def shutdown(self) -> None:
        """Operator stop (SIGTERM / tests). A halt never calls this."""
        self._stop.set()
        if self._serving:  # socketserver's shutdown() waits forever on a server that never served
            self.server.shutdown()
        self.server.server_close()


# -- x3-check: the live check -----------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a 3xx is an answer: the perimeter header must not travel


_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))

HttpCall = Callable[..., "tuple[int, Any]"]


def urllib_call(method: str, url: str, body: Any | None = None, *, secret: str | None = None,
                timeout: float = 20.0) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if secret:
        headers["x-field-auth"] = secret
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read() or b"", exc.code
    except Exception as exc:  # type name only, never a message
        return 0, {"transport_error": type(exc).__name__}
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, {"non_json_bytes": len(raw)}


def x3_check(agent: str, *, killswitch_url: str, registry_url: str, ledger_url: str,
             canary_url: str, platform: HttpCall, canary: HttpCall,
             out: Callable[[str], None] = print) -> int:
    """The X3 done-when, against a running estate. ``platform`` carries the
    perimeter secret; ``canary`` never does (the canary has no field authn,
    and a secret must not travel to it). Response bodies are never printed."""
    results: list[tuple[bool, str]] = []

    def check(ok: bool, label: str) -> bool:
        results.append((bool(ok), label))
        out(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        return bool(ok)

    def count(event_type: str) -> int | None:
        q = urllib.parse.urlencode({"event_type": event_type, "agent_id": agent})
        status, body = platform("GET", f"{ledger_url}/events?{q}")
        return len(body) if status == 200 and isinstance(body, list) else None

    if agent not in CANARIES:
        out(f"refusing: '{agent}' is not one of {sorted(CANARIES)} - X3 runs on the canary only (rule 7)")
        return 2
    q_agent = urllib.parse.quote(agent, safe="")
    status, rec = platform("GET", f"{registry_url}/agents/{q_agent}")
    if status != 200 or not isinstance(rec, dict) or rec.get("agent_id") != agent \
            or rec.get("domain") != CANARY_DOMAIN or rec.get("status") != "active":
        out(f"refusing: registry record for '{agent}' is not an active '{CANARY_DOMAIN}'-domain canary (HTTP {status})")
        return 2
    canary_host = urllib.parse.urlsplit(canary_url).hostname
    out(f"X3 halt endpoint live check - {agent} via {canary_host}")

    status, before = canary("GET", f"{canary_url}/status")
    check(status == 200 and isinstance(before, dict) and before.get("agent_id") == agent,
          f"canary-agent GET /status 200 for {agent} (got HTTP {status})")
    before = before if isinstance(before, dict) else {}
    check(before.get("heartbeat_every") == 0,
          f"heartbeat polling disabled for the test (heartbeat_every={before.get('heartbeat_every')})")
    halts0 = before.get("halts") if isinstance(before.get("halts"), int) else None

    nonce = secrets.token_hex(8)
    k0 = count("kill.endpoint_called")
    status, killed = platform("POST", f"{killswitch_url}/kill/{q_agent}",
                              {"operator": "FIELD gate verification (canary)", "reason": f"x3-{nonce}"})
    er = killed.get("endpoint_result") if isinstance(killed, dict) else None
    er = er if isinstance(er, dict) else {}
    check(status == 200 and er.get("outcome") == "called" and er.get("http_status") == 200
          and er.get("endpoint_host") == canary_host,
          f"kill reason x3-{nonce} => 200, endpoint_result outcome={er.get('outcome')} "
          f"reason={er.get('reason')} http_status={er.get('http_status')} host={er.get('endpoint_host')} "
          f"(want called 200 {canary_host})")
    k1 = count("kill.endpoint_called")
    check(k0 is not None and k1 == k0 + 1, f"exactly +1 kill.endpoint_called ({k0} -> {k1})")
    status, after = canary("GET", f"{canary_url}/status")
    after = after if isinstance(after, dict) else {}
    check(status == 200 and after.get("halted") is True and after.get("nonce") == nonce
          and after.get("last_halted_by") == "endpoint"
          and halts0 is not None and after.get("halts") == halts0 + 1 and bool(after.get("since")),
          f"canary-agent /status halted=true nonce={after.get('nonce')} (want {nonce}) "
          f"by={after.get('last_halted_by')} halts {halts0} -> {after.get('halts')}")

    r0 = count("kill.revive")
    status, _ = platform("POST", f"{killswitch_url}/revive/{q_agent}",
                         {"operator": "FIELD gate verification (canary)", "reason": f"x3-{nonce} revive"})
    r1 = count("kill.revive")
    check(status == 200 and r0 is not None and r1 == r0 + 1,
          f"revive 200 and exactly +1 kill.revive (HTTP {status}; {r0} -> {r1})")
    status, hb = platform("GET", f"{killswitch_url}/heartbeat/{q_agent}")
    check(status == 200 and isinstance(hb, dict) and hb.get("killed") is False,
          f"heartbeat killed=false after revive (HTTP {status})")
    status, still = canary("GET", f"{canary_url}/status")
    check(status == 200 and isinstance(still, dict) and still.get("halted") is True,
          "canary process still halted after revive (a revive flips the registry, not the process)")

    drill_nonce = secrets.token_hex(8)
    d0 = count("kill.drill.complete")
    status, drill = platform("POST", f"{killswitch_url}/drill/{q_agent}",
                             {"operator": "FIELD gate verification (canary)", "reason": f"x3-{drill_nonce}"})
    drill = drill if isinstance(drill, dict) else {}
    der = drill.get("endpoint_result") if isinstance(drill.get("endpoint_result"), dict) else {}
    ms = drill.get("endpoint_confirmed_ms")
    check(status == 200 and isinstance(ms, (int, float)) and not isinstance(ms, bool)
          and der.get("outcome") == "called" and drill.get("restored") is True
          and drill.get("restored_status") == "active",
          f"drill on the {CANARY_DOMAIN}-domain canary => endpoint_confirmed_ms={ms} outcome={der.get('outcome')} "
          f"restored={drill.get('restored')} {drill.get('restored_status')} (HTTP {status})")
    d1 = count("kill.drill.complete")
    check(d0 is not None and d1 == d0 + 1, f"exactly +1 kill.drill.complete ({d0} -> {d1})")
    status, final = canary("GET", f"{canary_url}/status")
    check(status == 200 and isinstance(final, dict) and final.get("nonce") == drill_nonce,
          f"canary-agent /status nonce={final.get('nonce') if isinstance(final, dict) else None} after the drill (want {drill_nonce})")

    failed = [label for ok, label in results if not ok]
    out(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for label in failed:
        out(f"  FAILED: {label}")
    return 1 if failed or not results else 0


# -- entry point -------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m field_agent.canary", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the canary agent (never exits on a halt)")
    serve.add_argument("--agent-id", default=os.environ.get("FIELD_CANARY_AGENT_ID", "canary-gb10"))
    serve.add_argument("--host", default=os.environ.get("FIELD_CANARY_HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("FIELD_CANARY_PORT", DEFAULT_PORT)))
    serve.add_argument("--work-every", type=float, default=_env_float("FIELD_CANARY_WORK_EVERY", 5.0))
    serve.add_argument("--heartbeat-every", type=float, default=_env_float("FIELD_CANARY_HEARTBEAT_EVERY", 0.0),
                       help="seconds between read-only heartbeat polls; 0 = off (default)")
    chk = sub.add_parser("x3-check", help="the X3 live check (run inside the kill-switch container)")
    chk.add_argument("--agent", required=True)
    chk.add_argument("--canary-url", default="http://canary-agent:8090")
    args = parser.parse_args(argv)

    if args.cmd == "x3-check":
        env = os.environ
        missing = [n for n in ("FIELD_KILLSWITCH_URL", "FIELD_REGISTRY_URL", "FIELD_LEDGER_URL") if not env.get(n)]
        if missing:
            print(f"refusing: {', '.join(missing)} unset (run inside the kill-switch container)")
            return 2
        secret = env.get("FIELD_SHARED_SECRET") or None
        return x3_check(
            args.agent,
            killswitch_url=env["FIELD_KILLSWITCH_URL"].rstrip("/"),
            registry_url=env["FIELD_REGISTRY_URL"].rstrip("/"),
            ledger_url=env["FIELD_LEDGER_URL"].rstrip("/"),
            canary_url=args.canary_url.rstrip("/"),
            platform=lambda m, u, b=None: urllib_call(m, u, b, secret=secret),
            canary=lambda m, u, b=None: urllib_call(m, u, b, secret=None),
        )

    agent = CanaryAgent(args.agent_id, host=args.host, port=args.port,
                        work_every=args.work_every, heartbeat_every=args.heartbeat_every)

    def _stop(signum: int, frame: Any) -> None:  # operator stop; a halt never gets here
        threading.Thread(target=agent.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _stop)
    print(f"canary-agent {args.agent_id} listening on {args.host}:{agent.port} "
          f"(heartbeat_every={args.heartbeat_every}, work_every={args.work_every})", flush=True)
    try:
        agent.serve_forever()
    except KeyboardInterrupt:
        agent.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
