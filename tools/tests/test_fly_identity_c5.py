"""Phase G C-5: per-process operator identities on Fly (integration/fly/entrypoint.sh).

The REAL entrypoint is RUN under bash with every launched service replaced by a recording stub (the same containment
as tools/topology_lint.py: PATH is a temp directory holding only the stubs and a logging wrapper around the real
mkdir, the only utility the entrypoint uses; cwd/HOME/TMPDIR in the temp dir). Each stub records its argv, the FIELD_OPERATOR* names and values it
inherited, its whole exported environment, and the content of the key file it was pointed at. Proven here:

* no identity secrets (today): every process gets byte-for-byte the environment, argv and utility calls of the
  origin/main entrypoint (14fed1e) and no key directory is made;
* the four FIELD_OPERATOR_KEY_<SVC> secrets set: each of killswitch, registry, delegation and lifecycle gets
  FIELD_OPERATOR=svc-<name> and FIELD_OPERATOR_KEY_FILE=<dir>/svc-<name>.key holding ITS key; no other process gets
  an identity; no process inherits any key value (the secrets are blanked); the key file is 0600 in a 0700 directory
  (POSIX runs; there is no chmod in the script, so the mode is the creation mode); no key appears in any argv,
  utility call or entrypoint output;
* a set-but-empty, whitespace, non-token or over-long secret, a partial set, or a machine-wide FIELD_OPERATOR /
  FIELD_OPERATOR_KEY / FIELD_OPERATOR_KEY_FILE stops the estate BEFORE any service starts and before any key file or
  directory is written, naming the secret only;
* FIELD_OPERATOR_REGISTRY naming a missing file is warned about once, and the services still start;
* every `<service> serve` line is byte-identical to origin/main, the topology lint's reviewed sets are unchanged
  (utilities == ["mkdir"]), and its "env -i on the first service" mutant still applies to the registry line.

Each guarantee has a mutant of the real script that turns its check RED (test_each_c5_mutant_is_caught).
tools/fly_identity_check.py (the in-machine checker CI and the Stage 4 scripts run) is tested on fake /proc trees.

The launch subshell's TERM trap (fly_wait_service, verbatim from the real script) is tested on its own: a subshell sent
TERM does not exit before its daemon has finished a slow TERM handler, and without the trap it does (review L3c).

NOT proven here: real Fly behaviour (secret injection, what PID 1 is, whether /run is tmpfs), real services reading
the key file (field-core's C-1 tests cover that), a machine restart, shutdown()'s own `kill -1` (it signals every
process, so it is only exercised in CI's container: fly-image-smoke stops estate-c5 and counts graceful shutdowns). CI's fly-image-smoke job runs the real image
with fake identity values; nothing here or there uses a real key.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import fly_identity_check as fic  # noqa: E402
import topology_lint as lint  # noqa: E402

ENTRY = REPO / "integration" / "fly" / "entrypoint.sh"
BASE_SHA = "14fed1eeb95ec3723756eca2e464a4646b078a58"   # origin/main before C-5 (Stage 0 deployed on both estates)
IN_CI = bool(os.environ.get("CI"))
POSIX_MODES = os.name != "nt"   # Git Bash on Windows cannot set or report 0600/0700 on NTFS

DAEMONS = {"killswitch": "svc-killswitch", "registry": "svc-registry", "delegation": "svc-delegation",
           "lifecycle": "svc-lifecycle"}
SECRETS = {d: "FIELD_OPERATOR_KEY_" + d.upper() for d in DAEMONS}
#: FAKE values in the key charset. Not keys: no registry row holds their hash.
FAKE = {d: f"c5FAKEnotakey-{d}-0001" for d in DAEMONS}
FOUR = {SECRETS[d]: FAKE[d] for d in DAEMONS}
IDENTITY_NAMES = ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE", *SECRETS.values())
LAUNCHED = tuple(lint.EXPECTED_FLY_STUBS)   # 13 services + caddy
UTILS = ("mkdir",)

_STUB = r"""#!/bin/sh
L="$C5_LOG/NAME"
printf '%s\n' "$0 $*" > "$L.argv"
export -p > "$L.export"
for v in VARS; do
  eval "s=\${$v+set} val=\${$v-}"
  printf '%s %s [%s]\n' "$v" "${s:-unset}" "$val" >> "$L.vars"
done
if [ -n "${FIELD_OPERATOR_KEY_FILE:-}" ] && [ -r "$FIELD_OPERATOR_KEY_FILE" ]; then
  "REALCAT" "$FIELD_OPERATOR_KEY_FILE" > "$L.keycontent"
fi
printf 'done\n' > "$L.done"
exec "REALSLEEP" 2
"""
_UTIL = r"""#!/bin/sh
printf '%s\n' "NAME $*" >> "$C5_LOG/utilities.log"
exec "REALUTIL" "$@"
"""


@pytest.fixture(scope="module")
def bash():
    found = lint.find_bash()
    if found is None:
        if IN_CI:
            pytest.fail("bash is required for the C-5 entrypoint tests in CI")
        pytest.skip("no bash found (set TOPOLOGY_LINT_BASH)")
    if not lint._honours_restricted_path(found):
        pytest.skip(f"{found} adds its own directories to PATH")
    return found


def _real(bash: str, name: str) -> str:
    for d in (str(Path(bash).parent), "/usr/bin", "/bin"):
        p = shutil.which(name, path=d)
        if p:
            return Path(p).as_posix()
    p = shutil.which(name)
    assert p, f"no real {name} for the wrappers"
    return Path(p).as_posix()


class Run:
    def __init__(self, td: Path, rc, out: str, err: str):
        self.td, self.rc, self.out, self.err = td, rc, out, err
        log = td / "log"
        self.started = sorted(p.name[:-5] for p in log.glob("*.argv"))
        self.argv = {n: (log / f"{n}.argv").read_text(encoding="utf-8").strip() for n in self.started}
        self.export = {n: (log / f"{n}.export").read_text(encoding="utf-8", errors="replace") for n in self.started}
        self.vars: dict[str, dict[str, tuple[str, str]]] = {}
        for n in self.started:
            d = {}
            for ln in (log / f"{n}.vars").read_text(encoding="utf-8").splitlines():
                m = re.fullmatch(r"(\S+) (set|unset) \[(.*)\]", ln)
                assert m, ln
                d[m.group(1)] = (m.group(2), m.group(3))
            self.vars[n] = d
        self.keycontent = {n: (log / f"{n}.keycontent").read_text(encoding="utf-8").strip()
                           for n in self.started if (log / f"{n}.keycontent").exists()}
        u = log / "utilities.log"
        self.utilities = u.read_text(encoding="utf-8").splitlines() if u.exists() else []
        self.key_dir = td / "keys"

    def norm(self, s: str) -> str:
        """The run's temp dir in every spelling (D:/x and Git Bash's /d/x) -> <TD>."""
        posix = self.td.as_posix()
        out = s.replace(posix, "<TD>")
        if re.match(r"^[A-Za-z]:/", posix):
            out = out.replace("/" + posix[0].lower() + posix[2:], "<TD>")
        return out

    def family(self, n: str) -> set[str]:
        """FIELD_OPERATOR* identity names in a stub's exported env (not the two flags)."""
        names = set(re.findall(r"\b(FIELD_OPERATOR\w*)=", self.export[n]))
        return names - {"FIELD_OPERATOR_REGISTRY", "FIELD_OPERATOR_REQUIRE"}


def run_entry(bash: str, tmp: Path, text: str, env_extra: dict[str, str] | None = None, timeout: float = 60.0) -> Run:
    td = tmp
    (td / "stubs").mkdir(parents=True)
    (td / "log").mkdir()
    for name in LAUNCHED:
        f = td / "stubs" / name
        f.write_text(_STUB.replace("NAME", name).replace("VARS", " ".join(IDENTITY_NAMES))
                     .replace("REALCAT", _real(bash, "cat")).replace("REALSLEEP", _real(bash, "sleep")),
                     encoding="utf-8", newline="\n")
        f.chmod(0o755)
    for name in UTILS:
        f = td / "stubs" / name
        f.write_text(_UTIL.replace("NAME", name).replace("REALUTIL", _real(bash, name)), encoding="utf-8", newline="\n")
        f.chmod(0o755)
    script = td / "entrypoint.sh"
    script.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    env = {k: v for k, v in os.environ.items()
           if k in ("SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "MSYSTEM", "LANG", "LC_ALL")}
    env.update(PATH=(td / "stubs").as_posix(), C5_LOG=(td / "log").as_posix(), FIELD_DATA_DIR=(td / "data").as_posix(),
               FIELD_FLY_KEY_DIR=(td / "keys").as_posix(), HOME=td.as_posix(), TMPDIR=td.as_posix(),
               TMP=td.as_posix(), TEMP=td.as_posix())
    env.update(env_extra or {})
    kwargs = {"start_new_session": True} if os.name != "nt" else {}
    p = subprocess.Popen([bash, script.as_posix()], env=env, cwd=str(td), stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", **kwargs)
    try:
        out, err = p.communicate(timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        rc = "TIMEOUT"
    # every started stub writes .done before it sleeps; wait for the ones that started
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        argv = {x.name[:-5] for x in (td / "log").glob("*.argv")}
        done = {x.name[:-5] for x in (td / "log").glob("*.done")}
        if argv <= done:
            break
        time.sleep(0.2)
    return Run(td, rc, out, err)


#: integration/fly/entrypoint.sh at BASE_SHA, frozen (CI's checkout is shallow, so `git show` cannot reach it there).
#: Not a .sh: tools/topology_lint.py treats every .sh mentioning FIELD_SHARED_SECRET as a deployment descriptor.
#: Compared with LF line endings (a Windows checkout with core.autocrlf may write CRLF).
BASE_FIXTURE = REPO / "tools" / "tests" / "fixtures" / "c5" / "fly-entrypoint-14fed1e.frozen"
BASE_SHA256 = "3470f1f0cd19273fcc9b47a37119b4b9df3fd857664727b5aa9fc1fc0ba7cbf6"


def _base_bytes() -> bytes:
    return BASE_FIXTURE.read_bytes().replace(b"\r\n", b"\n")


def _base_text() -> str:
    raw = _base_bytes()
    assert hashlib.sha256(raw).hexdigest() == BASE_SHA256, "the frozen origin/main entrypoint changed"
    return raw.decode("utf-8")


def test_the_frozen_base_is_not_a_lint_descriptor():
    assert "tools/tests/fixtures/c5/fly-entrypoint-14fed1e.frozen" not in lint.unclassified_descriptors(REPO)


def test_the_frozen_base_is_the_origin_main_entrypoint():
    """Where the clone has BASE_SHA (a full local clone), the fixture must equal it byte for byte."""
    try:
        r = subprocess.run(["git", "-C", str(REPO), "show", f"{BASE_SHA}:integration/fly/entrypoint.sh"],
                           capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"git unavailable: {exc}")
    if r.returncode != 0:
        pytest.skip(f"base commit {BASE_SHA} not in this (shallow) clone; the sha256 pin stands")
    assert r.stdout == _base_bytes()


REAL = ENTRY.read_text(encoding="utf-8").replace("\r\n", "\n")


# --- checks: each returns a list of problems (empty = holds); the mutants below must make one non-empty ----------

def problems_absent(r: Run, base: Run) -> list[str]:
    """No identity secrets: identical to origin/main, nothing new anywhere."""
    p = []
    if r.started != sorted(LAUNCHED) or base.started != sorted(LAUNCHED):
        p.append(f"started {r.started} (base {base.started})")
    for n in r.started:
        if r.norm(r.argv[n]) != base.norm(base.argv.get(n, "")):
            p.append(f"{n}: argv differs from origin/main")
        if r.norm(r.export[n]) != base.norm(base.export.get(n, "")):
            p.append(f"{n}: exported environment differs from origin/main")
        if r.family(n):
            p.append(f"{n}: carries {sorted(r.family(n))}")
    if [r.norm(u) for u in r.utilities] != [base.norm(u) for u in base.utilities]:
        p.append(f"utility calls differ: {r.utilities} vs {base.utilities}")
    if r.key_dir.exists():
        p.append("the key directory was created with no identity secrets")
    if "C-5" in r.err:
        p.append("the entrypoint printed a C-5 line with no identity secrets")
    return p


def problems_four(r: Run) -> list[str]:
    p = []
    if r.started != sorted(LAUNCHED):
        p.append(f"not every service started: {r.started} (exit {r.rc}; {r.err.strip()[-200:]!r})")
        return p
    kd = r.key_dir.as_posix()
    for n in r.started:
        v = r.vars[n]
        if n in DAEMONS:
            if v["FIELD_OPERATOR"] != ("set", DAEMONS[n]):
                p.append(f"{n}: FIELD_OPERATOR={v['FIELD_OPERATOR']}")
            if v["FIELD_OPERATOR_KEY_FILE"] != ("set", f"{kd}/{DAEMONS[n]}.key"):
                p.append(f"{n}: FIELD_OPERATOR_KEY_FILE={r.norm(v['FIELD_OPERATOR_KEY_FILE'][1])}")
            if r.keycontent.get(n) != FAKE[n]:
                p.append(f"{n}: its key file does not hold ITS key")
        else:
            for name in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY_FILE", "FIELD_OPERATOR_KEY"):
                if v[name][0] == "set":
                    p.append(f"{n}: has {name}")
            if n in r.keycontent:
                p.append(f"{n}: can name a key file")
        for s in SECRETS.values():
            if v[s][1]:
                p.append(f"{n}: inherited a value in {s}")
        for d, key in FAKE.items():
            if key in r.export[n] or key in r.argv[n]:
                p.append(f"{n}: the {d} key is in its environment or argv")
        if "FIELD_OPERATOR=" in r.export[n].replace("FIELD_OPERATOR_", "") and n not in DAEMONS:
            p.append(f"{n}: exports FIELD_OPERATOR")
    blob = r.out + r.err + "\n".join(r.utilities)
    for d, key in FAKE.items():
        if key in blob:
            p.append(f"the {d} key is in the entrypoint output or a utility argv")
    for d, op in DAEMONS.items():
        f = r.key_dir / f"{op}.key"
        if not f.is_file():
            p.append(f"{f.name} missing")
            continue
        if POSIX_MODES and stat.S_IMODE(f.stat().st_mode) != 0o600:
            p.append(f"{f.name}: mode {stat.S_IMODE(f.stat().st_mode):04o}")
    if POSIX_MODES and r.key_dir.is_dir() and stat.S_IMODE(r.key_dir.stat().st_mode) != 0o700:
        p.append(f"key directory mode {stat.S_IMODE(r.key_dir.stat().st_mode):04o}")
    want_utils = [f"mkdir -p {r.td.as_posix()}/data", f"mkdir -p {r.key_dir.as_posix()}"]
    if [r.norm(u) for u in r.utilities] != [r.norm(u) for u in want_utils]:
        p.append(f"utility calls are not exactly the data and key directory mkdir: {[r.norm(u) for u in r.utilities]}")
    if "per-process identities svc-killswitch, svc-registry, svc-delegation, svc-lifecycle" not in r.err:
        p.append("no C-5 start-up line naming the four identities")
    return p


def problems_refused(r: Run, secret: str) -> list[str]:
    p = []
    if r.started:
        p.append(f"services started: {r.started}")
    if r.rc in (0, "TIMEOUT"):
        p.append(f"exit {r.rc}")
    if "REFUSING TO START (Phase G C-5)" not in r.err or secret not in r.err:
        p.append(f"no loud refusal naming {secret}: {r.err.strip()[-300:]!r}")
    for key in FAKE.values():
        if key in r.out + r.err:
            p.append("a key value is in the refusal output")
    if r.key_dir.exists():
        p.append("a key directory or file was written before the refusal")
    return p


# --- the tests -----------------------------------------------------------------------------------------------------

def test_absent_secrets_are_byte_identical_to_origin_main(bash, tmp_path):
    base = run_entry(bash, tmp_path / "base", _base_text())
    r = run_entry(bash, tmp_path / "new", REAL)
    assert problems_absent(r, base) == []
    assert r.rc == base.rc == 1 and "a service exited" in r.err     # the supervisor's normal end in a stub run


def test_four_secrets_give_each_daemon_only_its_own_identity_and_key_file(bash, tmp_path):
    r = run_entry(bash, tmp_path, REAL, FOUR)
    assert problems_four(r) == []


def test_a_key_file_left_by_an_earlier_boot_is_rewritten_in_full(bash, tmp_path):
    """A container restarted with its filesystem finds the key files it wrote (0600) last time: they are truncated
    and rewritten with the current secret (a longer old value leaves nothing behind) and keep their 0600."""
    kd = tmp_path / "keys"
    kd.mkdir()
    if POSIX_MODES:
        kd.chmod(0o700)
    stale = kd / "svc-killswitch.key"
    stale.write_text("stale-old-value-much-longer-than-the-new-one-0123456789\n", encoding="utf-8")
    if POSIX_MODES:
        stale.chmod(0o600)
    r = run_entry(bash, tmp_path, REAL, FOUR)
    assert problems_four(r) == []
    assert stale.read_text(encoding="utf-8") == FAKE["killswitch"] + "\n"


@pytest.mark.parametrize("daemon", sorted(DAEMONS))
@pytest.mark.parametrize("value,why", [("", "empty"), ("   ", "whitespace"), ("two words", "not a token"),
                                       ("bad\tchar", "tab"), ("x" * 257, "too long"), ("quote'x", "quote")])
def test_an_unusable_secret_stops_the_estate_before_any_service(bash, tmp_path, daemon, value, why):
    r = run_entry(bash, tmp_path, REAL, {**FOUR, SECRETS[daemon]: value})
    assert problems_refused(r, SECRETS[daemon]) == [], why


@pytest.mark.parametrize("missing", sorted(DAEMONS))
def test_a_partial_set_stops_the_estate_naming_the_missing_secret(bash, tmp_path, missing):
    env = {k: v for k, v in FOUR.items() if k != SECRETS[missing]}
    r = run_entry(bash, tmp_path, REAL, env)
    assert problems_refused(r, SECRETS[missing]) == []
    assert "only 3 of the four" in r.err
    assert not r.key_dir.exists()            # refused before any key file is written


@pytest.mark.parametrize("name", ["FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE"])
@pytest.mark.parametrize("with_four", [False, True])
def test_a_machine_wide_identity_stops_the_estate(bash, tmp_path, name, with_four):
    env = {**(FOUR if with_four else {}), name: "svc-console" if name == "FIELD_OPERATOR" else "machinewideFAKE"}
    r = run_entry(bash, tmp_path, REAL, env)
    assert problems_refused(r, name) == []
    assert "machinewideFAKE" not in r.err


def test_a_blank_machine_wide_name_is_inert_and_not_refused(bash, tmp_path):
    r = run_entry(bash, tmp_path, REAL, {"FIELD_OPERATOR": ""})
    assert r.started == sorted(LAUNCHED)


def test_registry_path_missing_is_warned_and_the_services_still_start(bash, tmp_path):
    r = run_entry(bash, tmp_path / "missing", REAL, {"FIELD_OPERATOR_REGISTRY": "/data/operators/operators.json"})
    assert r.started == sorted(LAUNCHED)
    assert "WARNING (Phase G): FIELD_OPERATOR_REGISTRY names /data/operators/operators.json, which is not a file" in r.err
    present = tmp_path / "present-ops.json"
    present.write_text('{"operators": []}', encoding="utf-8")
    r2 = run_entry(bash, tmp_path / "present", REAL, {"FIELD_OPERATOR_REGISTRY": present.as_posix()})
    assert r2.started == sorted(LAUNCHED) and "FIELD_OPERATOR_REGISTRY names" not in r2.err
    r3 = run_entry(bash, tmp_path / "blank", REAL, {"FIELD_OPERATOR_REGISTRY": "  "})
    assert r3.started == sorted(LAUNCHED) and "FIELD_OPERATOR_REGISTRY names" not in r3.err


SERVE = re.compile(r"\b(\w+) serve --host 127\.0\.0\.1 --port \d+")


def test_every_serve_line_is_byte_identical_to_origin_main_and_identity_sits_only_on_the_four():
    real = REAL.splitlines()
    base_lines = [ln for ln in _base_text().splitlines() if SERVE.search(ln) and not ln.lstrip().startswith("#")]
    lines = [ln for ln in real if SERVE.search(ln) and not ln.lstrip().startswith("#")]
    assert len(lines) == len(base_lines) == 13
    assert lines == base_lines                         # the whole line, in the same order: no command line changed
    for i, ln in enumerate(real):
        if not SERVE.search(ln) or ln.lstrip().startswith("#"):
            continue
        svc = SERVE.search(ln).group(1)
        if svc in DAEMONS:
            assert real[i - 1] == f'( fly_identity_env {DAEMONS[svc]} "$fly_kf_{svc}"', (svc, real[i - 1])
            assert real[i + 1] == 'fly_wait_service "$!" ) &', (svc, real[i + 1])
        else:
            assert "fly_identity_env" not in real[i - 1] and "FIELD_OPERATOR" not in ln, ln
    # nothing exports an identity at the top level; the only export of FIELD_OPERATOR is inside fly_identity_env
    exports = [ln.strip() for ln in real if re.search(r"\bexport\b.*\bFIELD_OPERATOR(_KEY(_FILE)?)?=", ln)]
    assert exports == ['export FIELD_OPERATOR="$1" FIELD_OPERATOR_KEY_FILE="$2"'], exports
    assert REAL.count("fly_identity_env svc-") == 4


def test_the_topology_lint_reviewed_sets_and_first_launch_mutant_are_unchanged():
    """C-5 adds no utility (no chmod, no rm: the modes come from umask 077 at creation) and keeps the registry line
    literal, so test_topology_lint.py's pins (utilities == ["mkdir"], FIRST_LAUNCH = the registry line, whose
    "env -i" mutant must change the script) hold without editing that file."""
    scan = lint.scan_commands(REAL)
    assert scan.services == list(lint.EXPECTED_FLY_STUBS)
    assert scan.utilities == ["mkdir"]
    assert scan.indirect == []
    assert REAL.count("\nregistry serve --host 127.0.0.1 --port 8001 &\n") == 1


def test_the_topology_lint_still_runs_the_real_entrypoint_clean(bash):
    r = lint.run_entrypoint(REAL)
    assert r.ran and r.findings == [], (r.reason, r.findings)
    assert r.stubs == list(lint.EXPECTED_FLY_STUBS)


# --- mutants: each one of the real script must turn a check RED ------------------------------------------------------

def _mut(old: str, new: str, count: int = 1) -> str:
    assert REAL.count(old) >= 1, old
    return REAL.replace(old, new, count)


MUTANTS = {
    "secret not blanked: every child inherits the killswitch key": (
        _mut('    FIELD_OPERATOR_KEY_KILLSWITCH=""\n', ""), "four"),
    "identity exported in the parent: every later process presents svc-registry": (
        _mut('( fly_identity_env svc-registry "$fly_kf_registry"\n',
             'fly_identity_env svc-registry "$fly_kf_registry"\n(\n'), "four"),
    "identities swapped between two daemons": (
        _mut('( fly_identity_env svc-killswitch "$fly_kf_killswitch"',
             '( fly_identity_env svc-killswitch "$fly_kf_registry"'), "four"),
    "a key value in a start-up log line": (
        _mut('    [ -s "$fly_key_dir/$1.key" ] ||', '    echo "entrypoint: wrote $1 ($3)" >&2\n    [ -s "$fly_key_dir/$1.key" ] ||'),
        "four"),
    "a key value on a utility argv": (
        _mut('( umask 077 && mkdir -p "$fly_key_dir" )',
             '( umask 077 && mkdir -p "$fly_key_dir" "$fly_key_dir/$FIELD_OPERATOR_KEY_REGISTRY" )'), "four"),
    "a daemon left without its identity (the delegation block drops fly_identity_env)": (
        _mut('( fly_identity_env svc-delegation "$fly_kf_delegation"\n', '(\n'), "four"),
    "key file written outside the 0700 key directory": (
        _mut('fly_kf_lifecycle="$fly_key_dir/svc-lifecycle.key"', 'fly_kf_lifecycle="$fly_key_dir/../svc-lifecycle.key"'),
        "four"),
    "empty secret accepted": (_mut('    [ -n "$2" ] || fly_refuse "$1 is set but empty"\n', ""), "empty"),
    "token check removed": (
        _mut('        *[!A-Za-z0-9._~+/=-]*) fly_refuse', '        *[!A-Za-z0-9._~+/=\\ -]*) fly_refuse'), "space"),
    "all-or-none check removed (partial set starts unidentified)": (
        _mut('if [ "$fly_ids_set" -ne 0 ] && [ "$fly_ids_set" -ne 4 ]; then',
             'if false; then'), "partial"),
    "files written before every secret is validated": (
        _mut('    fly_key_check FIELD_OPERATOR_KEY_KILLSWITCH "$FIELD_OPERATOR_KEY_KILLSWITCH"\n',
             '    ( umask 077 && mkdir -p "$fly_key_dir" )\n'
             '    fly_key_write svc-killswitch FIELD_OPERATOR_KEY_KILLSWITCH "$FIELD_OPERATOR_KEY_KILLSWITCH"\n'
             '    fly_key_check FIELD_OPERATOR_KEY_KILLSWITCH "$FIELD_OPERATOR_KEY_KILLSWITCH"\n'), "empty"),
    "machine-wide FIELD_OPERATOR accepted": (
        _mut('fly_machine_wide FIELD_OPERATOR "${FIELD_OPERATOR-}"\n', ""), "machine-wide"),
    "identity exported even with no secrets": (
        _mut('    if [ -n "$2" ]; then\n        export FIELD_OPERATOR="$1" FIELD_OPERATOR_KEY_FILE="$2"\n    fi\n',
             '    export FIELD_OPERATOR="$1" FIELD_OPERATOR_KEY_FILE="$2"\n'), "absent"),
    "a launch command line changed": (
        _mut("killswitch serve --host 127.0.0.1 --port 8005 &", "killswitch serve --host 0.0.0.0 --port 8005 &"),
        "absent"),
    "key dir created with no secrets": (
        _mut('fly_kf_killswitch=""\n', 'fly_kf_killswitch=""\nmkdir -p "$fly_key_dir"\n'), "absent"),
    "a C-5 line printed with no secrets": (
        _mut('fly_kf_killswitch=""\n', 'fly_kf_killswitch=""\necho "entrypoint: Phase G C-5: nothing" >&2\n'), "absent"),
}
if POSIX_MODES:
    MUTANTS["no umask 077 on the key file: created 0644"] = (
        _mut("( umask 077 && printf", "( printf"), "four")
    MUTANTS["no umask 077 on the key directory: created 0755"] = (
        _mut('( umask 077 && mkdir -p "$fly_key_dir" )', '( mkdir -p "$fly_key_dir" )'), "four")


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_c5_mutant_is_caught(bash, tmp_path, name):
    text, kind = MUTANTS[name]
    if kind == "four":
        found = problems_four(run_entry(bash, tmp_path, text, FOUR))
    elif kind == "empty":
        found = problems_refused(run_entry(bash, tmp_path, text, {**FOUR, SECRETS["lifecycle"]: ""}),
                                 SECRETS["lifecycle"])
    elif kind == "space":
        found = problems_refused(run_entry(bash, tmp_path, text, {**FOUR, SECRETS["lifecycle"]: "two words"}),
                                 SECRETS["lifecycle"])
    elif kind == "partial":
        env = {k: v for k, v in FOUR.items() if k != SECRETS["killswitch"]}
        found = problems_refused(run_entry(bash, tmp_path, text, env), SECRETS["killswitch"])
    elif kind == "machine-wide":
        found = problems_refused(run_entry(bash, tmp_path, text, {"FIELD_OPERATOR": "svc-console"}), "FIELD_OPERATOR")
    else:
        base = run_entry(bash, tmp_path / "base", _base_text())
        found = problems_absent(run_entry(bash, tmp_path / "mut", text), base)
    assert found, f"mutant survived: {name}"


# --- tools/fly_identity_check.py on fake /proc trees -------------------------------------------------------------------

SERVICE_PORTS = {"registry": 8001, "ledger": 8002, "delegation": 8003, "sentinel": 8004, "killswitch": 8005,
                 "governor": 8006, "replay": 8007, "crosswalk": 8008, "forcegw": 8009, "fedbroker": 8010,
                 "console": 8011, "lifecycle": 8012, "attest": 8013}


def _proc(tmp: Path, key_dir: Path, mode: str, tweak=None) -> Path:
    """A fake /proc shaped like the C-5 entrypoint's process table (pid 1 = the entrypoint)."""
    proc = tmp / "proc"
    machine = {"FIELD_DATA_DIR": "/data", "FIELD_OPERATOR_REGISTRY": "", "FIELD_OPERATOR_REQUIRE": ""}
    if mode == "four":
        machine.update(FOUR)                         # Fly injects the secrets into the init environment
    procs = {1: (["/bin/bash", "/entrypoint.sh"], dict(machine))}
    pid = 100
    for svc, port in SERVICE_PORTS.items():
        env = dict(machine)
        if mode == "four":
            env.update({s: "" for s in SECRETS.values()})
            if svc in DAEMONS:
                env.update(FIELD_OPERATOR=DAEMONS[svc], FIELD_OPERATOR_KEY_FILE=f"{key_dir.as_posix()}/{DAEMONS[svc]}.key")
        procs[pid] = (["/usr/local/bin/python3.12", f"/usr/local/bin/{svc}", "serve", "--host", "127.0.0.1",
                       "--port", str(port)], env)
        pid += 1
    procs[900] = (["sh", "-c", "python3 /tmp/c5.py"], {**machine, "FIELD_SHARED_SECRET": "x"})   # the ssh session
    if mode == "four":
        key_dir.mkdir(parents=True)
        for d, op in DAEMONS.items():
            (key_dir / f"{op}.key").write_text(FAKE[d] + "\n", encoding="utf-8")
            if POSIX_MODES:
                (key_dir / f"{op}.key").chmod(0o600)
        if POSIX_MODES:
            key_dir.chmod(0o700)
    if tweak:
        tweak(procs, key_dir)
    for p, (argv, env) in procs.items():
        d = proc / str(p)
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        (d / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in env.items()) + b"\0")
    return proc


def _svc_pid(procs, svc):
    return next(p for p, (argv, _e) in procs.items() if f"/usr/local/bin/{svc}" in argv)


def _check(tmp: Path, mode: str, expect: str | None = None, tweak=None):
    kd = tmp / "keys"
    proc = _proc(tmp, kd, mode, tweak)
    problems, lines = fic.check(str(proc), expect or mode, kd.as_posix(), "999999")
    for key in FAKE.values():
        assert key not in "\n".join(problems + lines)        # the checker never prints a key
    return problems


def test_checker_passes_the_two_good_states(tmp_path):
    assert _check(tmp_path / "a", "none") == []
    if POSIX_MODES:
        assert _check(tmp_path / "b", "four") == []


def _skip_modes():
    if not POSIX_MODES:
        pytest.skip("file modes are not settable on this filesystem")


@pytest.mark.parametrize("name,mode,expect,tweak", [
    ("identity with no secrets", "none", "none",
     lambda procs, kd: procs[_svc_pid(procs, "console")][1].update(FIELD_OPERATOR="svc-killswitch")),
    ("key dir with no secrets", "none", "none", lambda procs, kd: kd.mkdir()),
    ("machine-wide FIELD_OPERATOR in pid 1", "none", "none", lambda procs, kd: procs[1][1].update(FIELD_OPERATOR="x")),
    ("a service missing", "none", "none", lambda procs, kd: procs.pop(_svc_pid(procs, "attest"))),
    ("a service twice", "none", "none",
     lambda procs, kd: procs.__setitem__(950, procs[_svc_pid(procs, "governor")])),
    ("four expected, none present", "none", "four", None),
    ("console has an identity", "four", "four",
     lambda procs, kd: procs[_svc_pid(procs, "console")][1].update(FIELD_OPERATOR="svc-killswitch")),
    ("a key value inherited by a service", "four", "four",
     lambda procs, kd: procs[_svc_pid(procs, "ledger")][1].update(FIELD_OPERATOR_KEY_KILLSWITCH=FAKE["killswitch"])),
    ("a daemon with the wrong id", "four", "four",
     lambda procs, kd: procs[_svc_pid(procs, "registry")][1].update(FIELD_OPERATOR="svc-killswitch")),
    ("a daemon with a raw key env", "four", "four",
     lambda procs, kd: procs[_svc_pid(procs, "delegation")][1].update(FIELD_OPERATOR_KEY="rawFAKE")),
    ("a key file missing", "four", "four", lambda procs, kd: (kd / "svc-lifecycle.key").unlink()),
    ("a key file empty", "four", "four", lambda procs, kd: (kd / "svc-lifecycle.key").write_text("\n")),
    ("two daemons share a key", "four", "four",
     lambda procs, kd: (kd / "svc-registry.key").write_text(FAKE["killswitch"] + "\n")),
    ("a key on a command line", "four", "four",
     lambda procs, kd: procs.__setitem__(951, (["helper", FAKE["registry"]], {}))),
])
def test_checker_fails_each_bad_state(tmp_path, name, mode, expect, tweak):
    if mode == "four":
        _skip_modes()
    assert _check(tmp_path, mode, expect, tweak), name


def test_checker_fails_loose_modes(tmp_path):
    _skip_modes()
    assert _check(tmp_path / "f", "four", tweak=lambda procs, kd: (kd / "svc-killswitch.key").chmod(0o644))
    assert _check(tmp_path / "d", "four", tweak=lambda procs, kd: kd.chmod(0o755))


def test_checker_health_expectations():
    good_none = {s: {"operator_identity_id": None, "identity_present": False} for s in fic.HEALTH_PREFIX}
    assert fic.check_health(good_none, "none") == []
    good_four = {s: ({"operator_identity_id": fic.DAEMONS[s], "identity_present": True} if s in fic.DAEMONS
                     else {"operator_identity_id": None, "identity_present": False}) for s in fic.HEALTH_PREFIX}
    assert fic.check_health(good_four, "four") == []
    assert fic.check_health(good_none, "four")
    assert fic.check_health(good_four, "none")
    bad = dict(good_four, console={"operator_identity_id": "svc-killswitch", "identity_present": True})
    assert fic.check_health(bad, "four")
    assert fic.check_health(dict(good_none, ledger={"_error": "URLError"}), "none")


def test_checker_health_identity_present_must_agree_with_the_id():
    """Review L3a: the right operator_identity_id with the wrong identity_present is a mismatch, in both modes."""
    good_four = {s: ({"operator_identity_id": fic.DAEMONS[s], "identity_present": True} if s in fic.DAEMONS
                     else {"operator_identity_id": None, "identity_present": False}) for s in fic.HEALTH_PREFIX}
    good_none = {s: {"operator_identity_id": None, "identity_present": False} for s in fic.HEALTH_PREFIX}
    assert fic.check_health(dict(good_four, killswitch={"operator_identity_id": "svc-killswitch",
                                                        "identity_present": False}), "four")
    assert fic.check_health(dict(good_four, ledger={"operator_identity_id": None, "identity_present": True}), "four")
    assert fic.check_health(dict(good_none, registry={"operator_identity_id": None, "identity_present": True}), "none")


def _simulated_posix_modes(monkeypatch, kd: Path):
    """Review L3b: on Windows (NTFS) the checker's four-mode cases stop at the 0600/0700 checks. Report those modes for
    the key directory and its files only, so the four-mode logic after the mode checks runs on every OS. The real mode
    checks stay covered by the POSIX-only cases above and by CI."""
    real = os.lstat

    def lstat(path, *a, **k):
        st = real(path, *a, **k)
        p = Path(os.fspath(path))
        if p == kd or p.parent == kd:
            mode = (st.st_mode & ~0o7777) | (0o700 if stat.S_ISDIR(st.st_mode) else 0o600)
            return os.stat_result((mode,) + tuple(st)[1:])
        return st
    monkeypatch.setattr(fic.os, "lstat", lstat)


@pytest.mark.parametrize("name,mode,expect,tweak", [
    ("none: a service inherits a blank FIELD_OPERATOR_KEY_<SVC> name", "none", "none",
     lambda procs, kd: procs[_svc_pid(procs, "governor")][1].update(FIELD_OPERATOR_KEY_LIFECYCLE="")),
    ("none: a service inherits a FIELD_OPERATOR_KEY_<SVC> value", "none", "none",
     lambda procs, kd: procs[_svc_pid(procs, "ledger")][1].update(FIELD_OPERATOR_KEY_REGISTRY="rawFAKE")),
    ("four: a key value inherited by a non-daemon", "four", "four",
     lambda procs, kd: procs[_svc_pid(procs, "ledger")][1].update(FIELD_OPERATOR_KEY_KILLSWITCH=FAKE["killswitch"])),
    ("four: a daemon also carries another daemon's secret", "four", "four",
     lambda procs, kd: procs[_svc_pid(procs, "registry")][1].update(FIELD_OPERATOR_KEY_LIFECYCLE=FAKE["lifecycle"])),
    ("four: two daemons share a key", "four", "four",
     lambda procs, kd: (kd / "svc-registry.key").write_text(FAKE["killswitch"] + "\n")),
])
def test_checker_inherited_and_shared_states_on_every_os(tmp_path, monkeypatch, name, mode, expect, tweak):
    _simulated_posix_modes(monkeypatch, tmp_path / "good" / "keys")
    assert _check(tmp_path / "good", mode) == [], "the good state must pass under simulated modes"
    _simulated_posix_modes(monkeypatch, tmp_path / "bad" / "keys")
    assert _check(tmp_path / "bad", mode, expect, tweak), name


#: Review L3c: shutdown()'s `kill -1` can only run in a PID namespace (CI's container), so the property it relies on
#: is tested here on fly_wait_service alone, taken verbatim from the real script: a launch subshell that gets TERM must
#: not exit before its daemon has finished its own TERM handling (the daemon below takes 2 s and then writes a marker).
_WAIT_HARNESS = r"""set -u
M="$1"; P="$2"
FWS
daemon() { trap 'sleep 2; echo done > "$M"; exit 0' TERM; while :; do sleep 0.1; done; }
( daemon & echo "$!" > "$P"; fly_wait_service "$!" ) &
sub=$!
i=0; while [ ! -s "$P" ] && [ "$i" -lt 100 ]; do sleep 0.05; i=$((i + 1)); done
sleep 0.5
kill -TERM "$sub" "$(cat "$P")"
wait "$sub"; rc=$?
if [ -e "$M" ]; then echo "MARKER_AT_WAIT=yes rc=$rc"; else echo "MARKER_AT_WAIT=no rc=$rc"; fi
i=0; while [ ! -e "$M" ] && [ "$i" -lt 80 ]; do sleep 0.1; i=$((i + 1)); done
"""


def _fly_wait_service(text: str) -> str:
    m = re.search(r"^fly_wait_service\(\) \{.*?^\}\n", text, re.M | re.S)
    assert m, "fly_wait_service() not found in the entrypoint"
    return m.group(0)


def _run_wait_harness(bash: str, tmp: Path, fws: str) -> str:
    tmp.mkdir(parents=True)
    script = tmp / "harness.sh"
    script.write_text(_WAIT_HARNESS.replace("FWS", fws), encoding="utf-8", newline="\n")
    env = dict(os.environ, PATH=str(Path(bash).parent) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([bash, script.as_posix(), (tmp / "marker").as_posix(), (tmp / "pid").as_posix()],
                       capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, env=env, cwd=str(tmp))
    return r.stdout.strip()


def test_a_launch_subshell_outlives_term_until_its_daemon_has_shut_down(bash, tmp_path):
    fws = _fly_wait_service(REAL)
    assert "trap " in fws
    assert _run_wait_harness(bash, tmp_path / "real", fws) == "MARKER_AT_WAIT=yes rc=0"
    # the mutant the reviewer found surviving locally (R8): without the trap the subshell dies at once
    mutant = fws.replace("""    trap 'wait "$fly_service_pid"; exit $?' TERM INT\n""", "")
    assert mutant != fws
    assert _run_wait_harness(bash, tmp_path / "mutant", mutant).startswith("MARKER_AT_WAIT=no ")


def test_checker_main_prints_a_result_line_and_never_a_value(tmp_path, capsys, monkeypatch):
    proc = _proc(tmp_path, tmp_path / "keys", "none")
    monkeypatch.setenv("PROC_ROOT", str(proc))
    assert fic.main(["--expect", "none", "--key-dir", (tmp_path / "keys").as_posix()]) == 0
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1] == "C5-RESULT: PASS expect=none"
    assert fic.main(["--expect", "four", "--key-dir", (tmp_path / "keys").as_posix()]) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("C5-RESULT: FAIL ")
