"""OPERATOR script — put Spin State's own agents on the GB10 FIELD estate.

Since v1.2 (B4) this is a **thin wrapper over `lifecycle provision`**: the
register / cap / mint sequence lives in
``lifecycle_manager.engine.LifecycleEngine.provision`` and this file no
longer does its own ``PUT /caps`` or ``POST /tokens``. What stays here is
the operator's side of the job that the CLI has no opinion about — the
single-port proxy contract, the estate health gate, the AGENTS table, the
token cache, and the post-provision probes that put real verdicts on the
ledger.

Provision is the SAME code path `lifecycle provision` runs, wired to the
proxy's path prefixes instead of per-service URLs. One consequence worth
knowing: an INVALID manifest stops the run for that agent with ZERO side
effects, and a failure part-way through is reported step by step — never
pretended atomic.

Registers ssl-timekeeping-agent and ssl-invoicing-agent, caps them from
their manifests, mints delegation tokens scoped EXACTLY to each manifest's
``delegation.scope``, then fires one sentinel /check per scope action plus
one never-granted action per agent so the verdicts land on the ledger.
Idempotent — safe to re-run (re-running mints fresh tokens; an already
registered agent is reported as ``updated``) on an estate that does not
require operator auth. Under FIELD_OPERATOR_REQUIRE see RE-PROVISION below.

This is the human's side of governance (bootstrap lives outside the agents;
see docs/INTEGRATION.md §3). It is the single-port-proxy analogue of
``_local-test/provision_local.py`` — that file is NOT dead: it lives
untracked in the PARENT folder, and its local path is now
``lifecycle provision`` too.

Run from rog-command (venv C:\\Users\\donal\\.venvs\\field-platform):

    python tools/provision_ssl_agents.py [--operator-id don --operator-key-file PATH]

Env:
    FIELD_PROXY_URL      default http://10.0.0.62:18080  (Caddy path-routed)
    FIELD_SHARED_SECRET  if the estate enforces x-field-auth
    FIELD_TOKENS_FILE    default %USERPROFILE%\\.field-local\\tokens-gb10.json
    FIELD_TOKEN_TTL_DAYS default 30
    FIELD_OPERATOR, FIELD_OPERATOR_KEY_FILE / FIELD_OPERATOR_KEY
                         the operator pair when the flags are not given

OPERATOR IDENTITY (Phase G C-2). --operator-id and --operator-key-file, else
the environment pair. The key file is read here and stripped; the key is never
an argument and never printed, and a broken key file named on the command line
exits 2 before anything is sent. The pair is sent ONLY on the guarded writes in
GUARDED_ROUTES (register, re-register, cap, rate limits, mint: RT1-10), never on
/health, a heartbeat, a sentinel /check or the ledger verify. Per design v0.4
section 2.2.1 this script runs as ``don``: the mint's granted_by stays each
manifest's ``identity.principal`` (Don's display name, an alias of the ``don``
row, which holds ``mint_for_others``), not a job id.

RE-PROVISION UNDER FIELD_OPERATOR_REQUIRE (PG0-CLI-R1-01). A first provision
works as ``don``. Re-running it for an agent that is already registered does
not: the registry answers 409 and the engine PATCHes the agent's ``owner`` and
``manifest_ref``, which needs the ``registry_edit`` scope, held only by
``don-admin`` in design v0.4 section 2.2.1 (``don`` and ``job-provision-gb10``
do not hold it, RT1-9). So that agent stops at the register step with a 403,
nothing after it runs, and the script exits 1: fail closed, no partial grant.
``don-admin`` cannot run it either (it lacks ``register``, ``caps`` and
``mint``), so under that table no single identity re-provisions a registered
agent; that is a scope decision for Don, not something this script chooses.
tools/tests/test_job_grantors_c13.py pins the 403 for ``don`` and
``job-provision-gb10``.

PREREQUISITE: install the two manifests on the estate at
/data/manifests/<agent>.yaml BEFORE provisioning (GB10: ``manifests-admin
install``; see manifests/README.md). Since v1.2 D3b the registry refuses a
``manifest_ref`` that does not resolve on its filesystem (POST /agents 422),
so without them the register step fails with that 422 and nothing after it
runs. A manifest removed after registration still makes every /check an
``I.manifest`` BLOCK (the sentinel resolves ``manifest_ref`` on ITS filesystem).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.parse

import httpx
import yaml

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
PROXY = os.environ.get("FIELD_PROXY_URL", "http://10.0.0.62:18080").rstrip("/")
REG, LED, DEL, SEN, KIL, GOV = (f"{PROXY}/{p}" for p in
                                ("registry", "ledger", "delegation",
                                 "sentinel", "killswitch", "governor"))
TTL_DAYS = int(os.environ.get("FIELD_TOKEN_TTL_DAYS", "30"))
TOKENS_FILE = pathlib.Path(os.environ.get(
    "FIELD_TOKENS_FILE",
    str(pathlib.Path.home() / ".field-local" / "tokens-gb10.json")))
ESTATE_MANIFEST_DIR = "/data/manifests"      # the sentinel's view, not ours

AGENTS = {
    "ssl-timekeeping-agent": {
        "name": "SSL Time Keeping Agent", "domain": "finance",
        "never": "submit for approval",
    },
    "ssl-invoicing-agent": {
        "name": "SSL Invoicing Agent", "domain": "finance",
        "never": "send invoice email",
    },
}

headers = {}
if os.environ.get("FIELD_SHARED_SECRET"):
    headers["x-field-auth"] = os.environ["FIELD_SHARED_SECRET"]
#: reads and probes: x-field-auth only, never the operator pair (RT1-10)
H = httpx.Client(timeout=20.0, headers=headers)

#: Phase G C-2: the ONLY (method, path under FIELD_PROXY_URL) pairs that carry the
#: operator pair: the guarded writes `lifecycle provision` makes. Checked against the
#: services' api.py by tools/tests/test_operator_cli_c2.py.
GUARDED_ROUTES = (
    ("POST", re.compile(r"/registry/agents")),
    ("PATCH", re.compile(r"/registry/agents/[^/]+")),
    # one entry for the two governor writes (cap, rate limits); written as an alternation so
    # this file still never names the cap path (lifecycle-manager test_provision_wrapper.py)
    ("PUT", re.compile(r"/governor/(?:caps|rate-limits)/[^/]+")),
    ("POST", re.compile(r"/delegation/tokens")),
)
_OPERATOR_ID = re.compile(r"[A-Za-z0-9._@-]{1,64}")
_OPERATOR_KEY = re.compile(r"[A-Za-z0-9._~+/=-]{1,256}")
_MAX_KEY_FILE_BYTES = 4096


def _refuse(message: str) -> None:
    print(f"refused: {message}", file=sys.stderr)
    raise SystemExit(2)


def _read_key_file(path: str, strict: bool) -> str:
    """The stripped key in ``path``; ``strict`` (named on the command line):
    any problem exits 2 before anything is sent. The content is never printed."""
    problem, key = None, ""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(_MAX_KEY_FILE_BYTES + 1)
    except OSError as exc:
        problem = f"unreadable ({type(exc).__name__})"
    else:
        if len(raw) > _MAX_KEY_FILE_BYTES:
            problem = "larger than a key"
        else:
            try:
                key = raw.decode("utf-8-sig").strip()
            except UnicodeDecodeError:
                problem = "not UTF-8"
            else:
                if not key:
                    problem = "empty"
                elif not _OPERATOR_KEY.fullmatch(key):
                    problem = "not a single key token"
    if problem:
        if strict:
            _refuse(f"--operator-key-file is {problem}; nothing sent")
        print(f"warning: FIELD_OPERATOR_KEY_FILE is {problem}; no operator identity is sent", file=sys.stderr)
        return ""
    return key


def operator_pair(operator_id: str | None, key_file: str | None) -> tuple[str, str] | None:
    """(id, key) or None. The flags win over the environment;
    FIELD_OPERATOR_KEY_FILE wins over FIELD_OPERATOR_KEY (an unusable file never
    falls back to the variable)."""
    explicit = operator_id is not None or key_file is not None
    op = (operator_id if operator_id is not None else os.environ.get("FIELD_OPERATOR", "")).strip()
    env_file = os.environ.get("FIELD_OPERATOR_KEY_FILE", "").strip()
    if key_file is not None:
        key = _read_key_file(key_file, strict=True)
    elif env_file:
        key = _read_key_file(env_file, strict=explicit) if (op or explicit) else ""
    else:
        key = os.environ.get("FIELD_OPERATOR_KEY", "")
    if explicit and not (op and key):
        _refuse("--operator-id and an operator key (--operator-key-file, FIELD_OPERATOR_KEY_FILE or "
                "FIELD_OPERATOR_KEY) go together; nothing sent")
    if not (op and key):
        return None
    if not _OPERATOR_ID.fullmatch(op):
        _refuse("the operator id is not a valid operator id; nothing sent")
    if not _OPERATOR_KEY.fullmatch(key):
        _refuse("the operator key is not a single key token (value not shown); nothing sent")
    return op, key


def is_guarded(method: str, path: str) -> bool:
    """True only for an allowlisted (method, path); ``path`` is relative to
    FIELD_PROXY_URL (a full URL path under it is accepted too)."""
    prefix = urllib.parse.urlsplit(PROXY).path.rstrip("/")
    if prefix and path.startswith(prefix + "/"):
        path = path[len(prefix):]
    path = urllib.parse.urlsplit(path).path
    return any(m == method.upper() and rx.fullmatch(path) for m, rx in GUARDED_ROUTES)


class _GuardedOperatorAuth(httpx.Auth):
    """The operator pair on allowlisted guarded writes only."""

    def __init__(self, pair: tuple[str, str] | None):
        self._pair = pair

    def auth_flow(self, request):
        if self._pair and is_guarded(request.method, request.url.path):
            request.headers["x-field-operator"], request.headers["x-field-operator-key"] = self._pair
        yield request


def client(pair: tuple[str, str] | None) -> httpx.Client:
    """The client for `lifecycle provision`'s writes: x-field-auth always, the
    operator pair only on GUARDED_ROUTES."""
    return httpx.Client(timeout=20.0, headers=headers, auth=_GuardedOperatorAuth(pair))


def manifest_path(agent_id: str) -> pathlib.Path:
    return REPO / "manifests" / f"{agent_id}.yaml"


def manifest(agent_id: str) -> dict:
    return yaml.safe_load(manifest_path(agent_id).read_text(encoding="utf-8"))


def health() -> None:
    bad = []
    for name, base in (("registry", REG), ("ledger", LED), ("delegation", DEL),
                       ("sentinel", SEN), ("killswitch", KIL), ("governor", GOV)):
        try:
            r = H.get(f"{base}/health")
            ok = r.status_code == 200
        except Exception as exc:              # noqa: BLE001 — report, then stop
            ok, r = False, exc
        print(f"  {name:11s} {'OK' if ok else 'FAIL'}  {base}")
        if not ok:
            bad.append(name)
    if bad:
        sys.exit(f"estate not healthy ({', '.join(bad)}) — nothing provisioned")


def build_engine(client: httpx.Client | None = None):
    """The same engine `lifecycle provision` builds, pointed at the proxy.

    ``client`` is an injection seam: a test hands in one in-process client so
    the whole wrapper runs with no network."""
    from field_core.clients import LedgerClient, RegistryClient
    from lifecycle_manager.engine import LifecycleEngine

    http = client or H
    return LifecycleEngine(
        registry=RegistryClient(client=http, base_url=REG),
        registry_http=_Prefixed(http, REG),
        delegation=_Prefixed(http, DEL),
        governor=_Prefixed(http, GOV),
        ledger=LedgerClient(client=http, base_url=LED),
    )


class _Prefixed:
    """Turn one shared client into a per-service one by prefixing the path.

    The engine calls relative paths (`/agents`, `/caps/{id}`, `/tokens`);
    behind the single-port Caddy proxy each service lives under its own path
    prefix, so the prefix is applied here rather than in the engine."""

    def __init__(self, client, base: str):
        self.client = client
        self.base = base.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    def get(self, path, **kw):
        return self.client.get(self._url(path), **kw)

    def post(self, path, **kw):
        return self.client.post(self._url(path), **kw)

    def put(self, path, **kw):
        return self.client.put(self._url(path), **kw)

    def patch(self, path, **kw):
        return self.client.patch(self._url(path), **kw)


def provision_agent(agent_id: str, meta: dict, engine=None):
    """One agent through `lifecycle provision`. Returns the ProvisionReport."""
    engine = engine or build_engine()
    m = manifest(agent_id)
    assert m["agent"]["name"] == agent_id, f"manifest name mismatch for {agent_id}"
    principal = m["identity"]["principal"]
    return engine.provision(
        manifest_path=manifest_path(agent_id),
        owner=principal,
        domain=meta["domain"],
        grantor=principal,
        ttl_days=TTL_DAYS,
        name=meta["name"],
        manifest_ref=f"{ESTATE_MANIFEST_DIR}/{agent_id}.yaml",
    )


def probe(agent_id: str, meta: dict, scope: list[str], token_id: str | None,
          client: httpx.Client | None = None) -> list[tuple[str, str, str]]:
    """Heartbeat + one sentinel /check per scope action, plus one action that
    was never granted. The verdicts are REAL and land on the ledger; the
    never-granted one is expected to refuse with `D.scope`.

    Returns `(action, decision, clause)` rows so a test can assert them."""
    http = client or H
    hb = http.get(f"{KIL}/heartbeat/{agent_id}").json()
    print(f"  heartbeat: killed={hb.get('killed')} status={hb.get('status')}")

    rows: list[tuple[str, str, str]] = []
    for action in list(scope) + [meta["never"]]:
        v = http.post(f"{SEN}/check", json={
            "agent_id": agent_id, "action": action,
            "token_id": token_id}).json()
        wb = (v.get("context") or {}).get("would_be") or {}
        clause = wb.get("clause_id") or v.get("clause_id") or "-"
        decision = v.get("decision", "?")
        tag = "" if action != meta["never"] else "   (never granted — expect D.scope)"
        print(f"    {action:30s} -> {decision:8s} {clause}{tag}")
        rows.append((action, decision, clause))
    return rows


def main(argv: list[str] | None = None) -> int:
    from lifecycle_manager.engine import LifecycleError

    # allow_abbrev=False: "--operator-key VALUE" must never be taken for --operator-key-file
    parser = argparse.ArgumentParser(description="Provision Spin State's own agents on the GB10 estate "
                                     "through lifecycle provision.", allow_abbrev=False)
    parser.add_argument("--operator-id", metavar="ID",
                        help="operator id (design: don), sent only on guarded writes (default: $FIELD_OPERATOR)")
    parser.add_argument("--operator-key-file", metavar="PATH",
                        help="file holding that operator's key; read and stripped here, never printed "
                             "(default: $FIELD_OPERATOR_KEY_FILE, else $FIELD_OPERATOR_KEY)")
    args = parser.parse_args(argv)
    pair = operator_pair(args.operator_id, args.operator_key_file)

    print(f"estate: {PROXY}")
    health()
    engine = build_engine(client(pair))
    tokens: dict[str, str] = {}
    if TOKENS_FILE.exists():
        tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))

    failed: list[str] = []
    for agent_id, meta in AGENTS.items():
        print(f"\n== {agent_id}")
        try:
            report = provision_agent(agent_id, meta, engine=engine)
        except LifecycleError as exc:
            print(f"  REFUSED: {exc}")
            failed.append(agent_id)
            continue
        for step in report.steps:
            detail = f" — {step.detail}" if step.detail else ""
            print(f"  {step.step:9s} {step.outcome:8s}{detail}")
        if not report.ok:
            # Explicitly NOT rolled back: say where it stopped and move on.
            print("  provision did not complete — earlier steps were NOT undone")
            failed.append(agent_id)
            continue
        if report.token_id:
            tokens[agent_id] = report.token_id
        probe(agent_id, meta, report.scope, report.token_id)

    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    print(f"\ntokens ({TTL_DAYS}-day TTL) saved to {TOKENS_FILE}")

    ver = H.get(f"{LED}/verify").json()
    print(f"ledger verify: {ver}")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
