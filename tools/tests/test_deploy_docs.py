"""Static checks of the Phase C deploy configuration and runbook text.

Nothing here runs docker: the compose-upgrade-smoke job and the runbook's
docker commands are executed only by CI and by an operator. What can be
checked without docker is that the text says the right thing, and each check
below fails on the text an adversarial review found wrong (2026-09-13 fix
round):

- the CI job examines EVERY platform container for the read-only manifests
  mount, and every non-ledger one for the absence of the keys volume (INF-2),
  and the X4 witness for a read-only keys mount;
- the job's non-manifest install control pins the refusal (exit 2 and the
  resolver's reason), not any non-zero exit (INF-10);
- the GB10 override mounts field-manifests read-only into every platform
  service and field-keys into the ledger and the X4 witness only (read-only);
  the witness has no port and no field-data, runs the spec'd command, and sits
  behind the compose profile `witness`, so no plain `up` arms A5; lifecycle's
  FIELD_WITNESS_EVERY is blank unless A5 sets it (blank = no witness finding),
  and the runbook arms and disarms the witness only through the profile + .env;
- the runbook's build commands bake FIELD_BUILD_SHA and its verify steps
  check it, on both estates (INF-7);
- the runbook backs up the field-manifests volume, carries it back before a
  pre-Phase-C compose rollback, and never gates a backup on a line count of
  the open ledger segment (INF-4, C2PD-5);
- no operator example puts a roster under /data/manifests (INF-5);
- Phase D wiring (2026-09-13): crosswalk egress is daily on both estates and
  nothing on the command line can override the variable its reader reads (Don's
  decision 3); compose no longer passes --mock, CI proves a real gateway
  roundtrip with the gateway's own mock model id and a keyless 502 elsewhere;
  FORCE_GATEWAY_URL / FIELD_FEDERATION_URL reach both estates under the names
  their readers use; the canaries declare the D-gate throttle; the runbook
  states that the D1 governor migration runs at open, with a down-migration
  naming exactly what the D1 store adds, and the governor-before-sentinel order.
- X3 (A6): the GB10 override runs `canary-agent` behind the profile `x3` from
  the platform Dockerfile (which installs packages/field-agent), with no port,
  no volumes and heartbeat polling off by default; the allowlist is blank in
  every compose default and on Fly (which gets nothing until D7); the GB10
  canary manifest names `http://canary-agent:8090/halt`; the runbook arms A6
  scoped (profile, then the allowlist, then the x3-check) and disarms the
  allowlist BEFORE the process.

Whether the commands WORK is not proven here; the fix round's scratch
evidence ran the non-docker halves (tar/sha256sum/cp/openssl, the ledger merge
with db5ad33 and Phase C code), and the docker halves are unexecuted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "runbooks" / "v1.2-deploy-rollback.md"


class _ComposeLoader(yaml.SafeLoader):
    pass


_ComposeLoader.add_constructor(
    "!override", lambda loader, node: loader.construct_sequence(node)
    if isinstance(node, yaml.SequenceNode) else loader.construct_scalar(node))


def _compose(name: str) -> dict:
    return yaml.load((REPO / "integration" / "demo" / name).read_text(encoding="utf-8"), Loader=_ComposeLoader)


def _platform_services() -> list[str]:
    return sorted(s for s in _compose("docker-compose.yml")["services"] if s != "proxy")


def _upgrade_job_step(fragment: str) -> str:
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    runs = [s["run"] for s in ci["jobs"]["compose-upgrade-smoke"]["steps"] if fragment in s.get("run", "")]
    assert len(runs) == 1, fragment
    return runs[0]


def _mount_checks(run: str) -> set[tuple[str, str, str]]:
    """(service, path, ro|absent) for every check_mount.py call the step makes."""
    checked = set()
    for loop in re.finditer(r"for svc in ([^;]+); do\n(.*?)\n\s*done", run, re.S):
        for call in re.finditer(r'exec -T "\$svc" python - (\S+) (ro|absent) <', loop.group(2)):
            checked |= {(svc, call.group(1), call.group(2)) for svc in loop.group(1).split()}
    for call in re.finditer(r"exec -T ([a-z][\w-]*) python - (\S+) (ro|absent) <", run):
        checked.add(call.groups())
    return checked


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8").replace("\r\n", "\n")


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


# --- CI: compose-upgrade-smoke ------------------------------------------------------------


def test_the_upgrade_job_checks_every_container_for_ro_manifests_and_every_reader_for_no_keys():
    checked = _mount_checks(_upgrade_job_step("check_mount.py"))
    services = _platform_services()
    assert len(services) == 13
    assert {s for s, p, w in checked if (p, w) == ("/data/manifests", "ro")} == set(services)
    assert {s for s, p, w in checked if (p, w) == ("/data/keys", "ro")} == {"ledger", "witness"}
    assert {s for s, p, w in checked if (p, w) == ("/data/keys", "absent")} == set(services) - {"ledger"}
    # the witness is behind its profile, so the job's plain `up` never started it: bring it up first
    run = _upgrade_job_step("check_mount.py")
    assert run.index("$COMPOSE --profile witness up -d --no-deps witness\n") < run.index("exec -T witness python")


def test_the_upgrade_job_pins_the_non_manifest_refusal_to_exit_2_and_the_resolver_reason():
    run = _upgrade_job_step("install doa-roster.example.yaml")
    assert re.search(r'out=\$\(\$COMPOSE run --rm -T manifests-admin install doa-roster\.example\.yaml 2>&1\)', run)
    assert 'test "$rc" -eq 2' in run
    assert 'grep -q "doa-roster.example.yaml would not resolve for a reader" <<<"$out"' in run
    # the message the job greps is the one volume_admin prints for that file
    assert "would not resolve for a reader" in (REPO / "tools" / "volume_admin.py").read_text(encoding="utf-8")


def test_the_gb10_override_mounts_manifests_ro_everywhere_and_keys_into_the_ledger_only():
    gb10 = _compose("docker-compose.gb10.yml")["services"]
    for svc in _platform_services():
        volumes = gb10[svc]["volumes"]
        assert "field-data:/data" in volumes, svc
        assert "field-manifests:/data/manifests:ro" in volumes, svc
        assert any(v.startswith("field-keys:") for v in volumes) == (svc == "ledger"), svc
        assert gb10[svc]["depends_on"]["manifests-admin"]["condition"] == "service_completed_successfully"
    assert "field-keys:/data/keys:ro" in gb10["ledger"]["volumes"]
    readers = {s for s, spec in gb10.items() if any(str(v).startswith("field-keys:") for v in spec.get("volumes", []))}
    assert readers == {"ledger", "witness", "keys-admin"}  # keys-admin: the writer, profile admin


def test_the_gb10_override_runs_the_x4_witness_scoped_and_least_privileged():
    base, gb10 = _compose("docker-compose.yml")["services"], _compose("docker-compose.gb10.yml")["services"]
    assert "witness" not in base
    wit = gb10["witness"]
    # A5 is its own switch: no plain `up` (deploy step 9, R1, CI) starts the witness
    assert wit["profiles"] == ["witness"]
    assert wit["command"] == ("ledger witness run --estate gb10 --fly-url https://force-field-sandbox.fly.dev "
                              "--every ${FIELD_WITNESS_EVERY:-3600}")
    assert wit["build"]["dockerfile"] == base["ledger"]["build"]["dockerfile"] == "integration/demo/Dockerfile"
    assert wit["build"]["args"] == {"FIELD_BUILD_SHA": "${FIELD_BUILD_SHA:-unknown}"}
    # no field-data: it writes through the served route; F2b adds its own read-only caller key mount
    assert wit["volumes"] == ["field-keys:/data/keys:ro",
                              "${FIELD_CALLER_KEYS_DIR:-/home/spinner/.field-local/caller-keys}/witness:/run/caller-key:ro"]
    assert "ports" not in wit and wit["restart"] == "unless-stopped" and wit["depends_on"] == ["ledger"]
    assert wit["environment"] == {
        "FIELD_LEDGER_URL": "http://ledger:8002",
        "FIELD_SHARED_SECRET": "${FIELD_SHARED_SECRET:-}",
        "FIELD_LEDGER_ANCHOR_KEY": "${FIELD_LEDGER_ANCHOR_KEY:-}",
        "FIELD_WITNESS_FLY_SECRET_FILE": "${FIELD_WITNESS_FLY_SECRET_FILE:-}",
        # F2b: the witness signs its appends as `witness` with its own mounted key
        "FIELD_LEDGER_CALLER_ID": "witness",
        "FIELD_LEDGER_CALLER_KEY": "/run/caller-key/witness.pem",
    }
    # blank unless A5 sets it: an estate whose witness is not armed (or was disarmed) never gets
    # the finding; set, the sweep reads the same variable the witness command runs with
    assert gb10["lifecycle"]["environment"] == {"FIELD_WITNESS_EVERY": "${FIELD_WITNESS_EVERY:-}",
                                                 "FIELD_LEDGER_CALLER_ID": "lifecycle",
                                                 "FIELD_LEDGER_CALLER_KEY": "/run/caller-key/lifecycle.pem"}
    assert [k for k in gb10 if gb10[k].get("profiles") is None and "FIELD_WITNESS_EVERY:-3600" in str(gb10[k])] == []


def test_the_runbook_arms_and_disarms_the_witness_only_through_its_profile():
    text = _runbook()
    step9 = _section(text, "9. **Bring v1.2 up", "10. **Copy the quiesced backup")
    assert "compose profile `witness`" in step9 and "<none>:anchor.remote" in step9
    a5 = _section(text, "### X4 witness (A5)", "## 5. Fly deploy")
    arm, disarm = a5[:a5.index("**Disarm, scoped:**")], a5[a5.index("**Disarm, scoped:**"):]
    switch = "printf '\\nCOMPOSE_PROFILES=witness\\nFIELD_WITNESS_EVERY=3600\\n' >> integration/demo/.env"
    assert switch in arm
    before, after = arm.index("# BEFORE: must print nothing"), arm.index("# AFTER: must print \"witness\"")
    assert before < arm.index(switch) < after < arm.index("$C up -d --no-deps --no-build witness lifecycle")
    assert disarm.index("$C stop witness") < disarm.index("delete BOTH lines") < disarm.index(
        "$C up -d --no-deps --no-build lifecycle")
    assert "starts it again (it is part of the GB10 topology)" not in text


# --- runbook: build SHA on both estates ----------------------------------------------------


def test_every_runbook_build_bakes_the_sha_and_every_verify_checks_it():
    text = _runbook()
    builds = [line for line in text.splitlines() if re.search(r"docker compose \$F build", line)]
    assert builds and all("FIELD_BUILD_SHA=$(git rev-parse HEAD) docker compose $F build" in b for b in builds)
    fly_builds = [line for line in text.splitlines() if "--build-only" in line]
    assert fly_builds and all("--build-arg FIELD_BUILD_SHA=$(git rev-parse HEAD)" in b for b in fly_builds)
    fly = _section(text, "## 5. Fly deploy", "## 6. Fly rollback")
    assert fly.count("--expect-build-sha") >= 2  # the smoke machine and the deployed machine
    assert "--expect-build-sha" in _section(text, "### 2.3 Verify", "### 2.4 Abort")


# --- runbook: manifests volume and the rotated ledger ----------------------------------------


def test_the_quiesced_backup_covers_the_manifests_volume_and_verifies_before_promoting():
    step8 = _section(_runbook(), "8. **Quiesced backup", "9. **Bring v1.2 up")
    backup = step8[step8.index("field-platform_field-manifests"):]
    assert backup.index("gzip -t \"$M.partial\"") < backup.index("diff - \"$M.sums\"") < backup.index("mv \"$M.partial\" \"$M\"")
    assert "RESTORE_SOURCE_MANIFESTS" in backup


def test_no_backup_gate_counts_lines_of_the_open_segment():
    text = _runbook()
    assert not re.search(r"wc -l[^\n]*events\.jsonl", re.sub(r"Never `wc -l[^`]*`", "", text))
    step8 = _section(text, "8. **Quiesced backup", "9. **Bring v1.2 up")
    assert "ledger verify --path /v/ledger/events.jsonl" in step8 and "health_info()" in step8


def test_r1_carries_the_manifests_back_before_the_compose_files_are_reverted():
    r1 = _section(_runbook(), "### R1 — code rollback", "### R2 — full data restore")
    carry = r1.index("cp -a /m/. /data/manifests/")
    assert carry < r1.index("sha256sum -c --quiet") < r1.index("git reset --hard pre-<phase>-gb10")


def test_the_rotated_ledger_rules_come_before_r1():
    text = _runbook()
    block = _section(text, "### After the C-gate rotation", "### R1 — code rollback")
    assert "fix forward" in block
    # the rotate CLI runs inside the container/machine: its --anchors path must be on the
    # persisted /data volume, then copied off-host (docker cp + scp; fly ssh sftp get)
    assert "--anchors /data/rotation-anchors/rotation-anchors-gb10.jsonl" in block
    assert "--anchors /data/rotation-anchors/rotation-anchors-fly.jsonl" in block
    assert "docker cp field-platform-ledger-1:/data/rotation-anchors/rotation-anchors-gb10.jsonl" in block
    assert "scp gx10:field-backups/rotation-anchors-gb10.jsonl" in block
    assert "fly ssh sftp get /data/rotation-anchors/rotation-anchors-fly.jsonl" in block
    text_without_warning = block.replace("`~/field-backups/...`", "")
    assert not re.search(r"--anchors\s+~", text_without_warning)
    # the merge is verified by the OLD image, from GENESIS, before anything is swapped
    assert block.index("$OLD ledger verify --path /data/ledger/.merged-events.jsonl") < block.index("mv ledger/.merged-events.jsonl")


# --- rosters ------------------------------------------------------------------------------------


@pytest.mark.parametrize("rel", [".env.example", "docs/INTEGRATION.md", "manifests/doa-roster.example.yaml"])
def test_no_operator_example_keeps_a_roster_under_data_manifests(rel):
    text = (REPO / rel).read_text(encoding="utf-8")
    assert not re.search(r"ROSTER=/data/manifests/", text)
    assert "ROSTER=/data/doa-roster.yaml" in text or "ROSTER=/data/owners.csv" in text


# --- Phase D wiring (v1.2 D1-D5; Don's decisions of 2026-09-13) ---------------------------------

FLY = REPO / "integration" / "fly"


def _entrypoint() -> str:
    return (FLY / "entrypoint.sh").read_text(encoding="utf-8").replace("\r\n", "\n")


def _ci_steps(job: str) -> list[dict]:
    return yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"][job]["steps"]


def test_crosswalk_regwatch_egress_is_daily_on_both_estates():
    """Decision 3: FIELD_CROSSWALK_EVERY=86400 on the GB10 (compose) and on Fly (entrypoint),
    reaching `crosswalk serve` through the envvar its --every option reads."""
    import tomllib

    import typer.main
    from compliance_crosswalk.cli import app as crosswalk_app

    every = [p for p in typer.main.get_command(crosswalk_app).commands["serve"].params if p.name == "every"]
    assert len(every) == 1 and every[0].envvar == "FIELD_CROSSWALK_EVERY"

    base, gb10 = _compose("docker-compose.yml"), _compose("docker-compose.gb10.yml")["services"]
    assert base["x-service"]["environment"]["FIELD_CROSSWALK_EVERY"] == "${FIELD_CROSSWALK_EVERY:-86400}"
    assert gb10["sentinel"]["environment"]["FIELD_CROSSWALK_EVERY"] == "${FIELD_CROSSWALK_EVERY:-86400}"
    crosswalk = base["services"]["crosswalk"]
    assert crosswalk["command"] == "crosswalk serve --host 0.0.0.0 --port 8008"  # no --every to override the env
    # the crosswalk's env is the anchor's (YAML merge); the GB10 override adds only its F2b caller key
    assert crosswalk["environment"]["FIELD_CROSSWALK_EVERY"] == "${FIELD_CROSSWALK_EVERY:-86400}"
    assert "FIELD_CROSSWALK_EVERY" not in gb10["crosswalk"].get("environment", {})

    entry = _entrypoint()
    assert 'export FIELD_CROSSWALK_EVERY="${FIELD_CROSSWALK_EVERY:-86400}"' in entry
    # v1.2 F1: the line carries the crosswalk's own identity as per-process env; still one line
    cw_lines = re.findall(r"^(?:[A-Z_]+=\S* )*crosswalk serve .*$", entry, re.M)
    assert len(cw_lines) == 1 and cw_lines[0].endswith("crosswalk serve --host 127.0.0.1 --port 8008 &")
    fly_env = tomllib.loads((FLY / "fly.toml").read_text(encoding="utf-8")).get("env", {})
    assert "FIELD_CROSSWALK_EVERY" not in fly_env  # the entrypoint default stands on Fly


def test_compose_drops_mock_and_ci_proves_the_gateway_roundtrip_and_the_keyless_502():
    from force_gateway.api import mock_upstream

    forcegw = _compose("docker-compose.yml")["services"]["forcegw"]
    assert "--mock" not in forcegw["command"]
    assert forcegw["environment"]["FORCE_GATEWAY_MOCK"] == "${FORCE_GATEWAY_MOCK:-}"
    assert forcegw["environment"]["ANTHROPIC_API_KEY"] == "${ANTHROPIC_API_KEY:-}"
    # v1.2 F1: the line carries the gateway's own identity as per-process env
    # (FIELD_SELF_AGENT_ID / FIELD_SELF_TOKEN_ID); still exactly one line, no --mock.
    forcegw_lines = re.findall(r"^(?:[A-Z_]+=\S* )*forcegw serve .*$", _entrypoint(), re.M)
    assert len(forcegw_lines) == 1 and "--mock" not in forcegw_lines[0]
    assert forcegw_lines[0].endswith("forcegw serve --host 127.0.0.1 --port 8009 &")

    smoke = _ci_steps("compose-smoke")
    runs = [s.get("run", "") for s in smoke]
    up = [i for i, r in enumerate(runs) if "docker compose up -d" in r]
    assert len(up) == 1 and "FORCE_GATEWAY_MOCK=1 docker compose up -d" in runs[up[0]]
    roundtrip = [i for i, r in enumerate(runs) if "/gateway/v1/messages" in r]
    assert len(roundtrip) == 1 and up[0] < roundtrip[0]
    model = mock_upstream({}, {})[1]["model"]
    assert f'test "$MODEL" = "{model}"' in runs[roundtrip[0]]  # a real POST answered by the mock, not /health
    assert "t['total_requests']==1" in runs[roundtrip[0]]

    for job in ("fly-image-smoke", "compose-upgrade-smoke"):
        keyless = [s["run"] for s in _ci_steps(job) if "/gateway/v1/messages" in s.get("run", "")]
        assert len(keyless) == 1, job
        assert 'test "$code" = 502' in keyless[0] and "grep -q ANTHROPIC_API_KEY" in keyless[0], job
        assert "h['mock'] is False" in keyless[0], job


def test_platform_llm_callers_and_federation_reach_both_estates_under_their_readers_names():
    from field_core import llm

    assert llm.GATEWAY_URL_ENV == "FORCE_GATEWAY_URL"
    federation_src = (REPO / "packages" / "field-agent" / "src" / "field_agent" / "federation.py").read_text(encoding="utf-8")
    assert '"FIELD_FEDERATION_URL"' in federation_src

    anchor = _compose("docker-compose.yml")["x-service"]["environment"]
    assert anchor["FORCE_GATEWAY_URL"] == anchor["FIELD_GATEWAY_URL"] == "http://forcegw:8009"
    assert anchor["FIELD_FEDERATION_URL"] == "http://fedbroker:8010"
    # the GB10 sentinel's restated env must stay its FULL env: every anchor key is there
    sentinel = _compose("docker-compose.gb10.yml")["services"]["sentinel"]["environment"]
    assert set(anchor) <= set(sentinel)
    assert sentinel["FORCE_GATEWAY_URL"] == "http://forcegw:8009"

    entry = _entrypoint()
    assert 'export FORCE_GATEWAY_URL="${FORCE_GATEWAY_URL:-http://127.0.0.1:8009}"' in entry
    assert 'export FIELD_FEDERATION_URL="${FIELD_FEDERATION_URL:-http://127.0.0.1:8010}"' in entry


def test_both_canaries_declare_the_d_gate_throttle_the_governor_accepts():
    from field_core.manifest import FieldManifest
    from field_core.validation import ValidationStatus, load_manifest, validate_manifest_file
    from spend_governor.provisioning import rate_limits_from_manifest

    for agent in ("canary-gb10", "canary-fly"):
        path = REPO / "manifests" / f"{agent}.yaml"
        assert validate_manifest_file(path).status is ValidationStatus.VALID, agent
        manifest = FieldManifest.from_dict(load_manifest(path))
        assert "canary.throttle" in manifest.delegation.scope, agent
        limits = rate_limits_from_manifest(manifest, agent)
        assert [(r.action, r.max, r.period) for r in limits.rate_limits] == [("canary.throttle", 3, "hourly")], agent


def test_the_runbook_states_the_d1_governor_migration_runs_at_open_and_the_deploy_order():
    from spend_governor import core

    text = _runbook()
    table = _section(text, "## 0. What can and cannot be undone", "**Fix-forward rule.**")
    rows = [line for line in table.splitlines() if "Spend-governor D1 migration" in line]
    assert len(rows) == 1 and "RUNS AT OPEN" in rows[0]
    # the down-migration names exactly what the D1 store adds at open, index first
    added = [column for column, _ in core._SPEND_ATTRIBUTION_COLUMNS]
    assert added == ["action", "source"]
    assert "idx_spend_agent_action_ts" in core._SPEND_ACTION_INDEX
    drops = re.findall(r"ALTER TABLE spend DROP COLUMN (\w+)", rows[0])
    assert sorted(drops) == sorted(added)
    assert rows[0].index("DROP INDEX idx_spend_agent_action_ts") < rows[0].index("DROP COLUMN")
    step9 = _section(text, "9. **Bring v1.2 up", "10. **Copy the quiesced backup")
    assert "spend-governor is recreated with or before" in step9 and "sentinel.metering_gap" in step9
    verify = _section(text, "### 2.3 Verify", "### 2.4 Abort")
    assert "keyless-real" in verify and "502" in verify


# --- X3: the canary-agent halt endpoint (GB10 only, arming step A6) -----------------------------


def test_the_gb10_override_runs_the_x3_canary_agent_scoped_with_no_port_and_no_data():
    base, gb10 = _compose("docker-compose.yml"), _compose("docker-compose.gb10.yml")["services"]
    assert "canary-agent" not in base["services"]
    agent = gb10["canary-agent"]
    # its own switch: no plain `up` (deploy step 9, R1, CI) builds or starts it before its arming
    assert agent["profiles"] == ["x3"]
    assert agent["build"]["dockerfile"] == base["services"]["ledger"]["build"]["dockerfile"] == "integration/demo/Dockerfile"
    assert agent["build"]["args"] == {"FIELD_BUILD_SHA": "${FIELD_BUILD_SHA:-unknown}"}
    assert agent["command"] == ["python", "-m", "field_agent.canary", "serve", "--agent-id", "canary-gb10", "--port", "8090"]
    assert "ports" not in agent and "expose" not in agent and "volumes" not in agent and "network_mode" not in agent
    assert agent["restart"] == "unless-stopped"
    assert agent["environment"] == {
        "FIELD_CANARY_HEARTBEAT_EVERY": "${FIELD_CANARY_HEARTBEAT_EVERY:-0}",  # polling OFF unless set
        "FIELD_KILLSWITCH_URL": "http://killswitch:8005",
        "FIELD_SHARED_SECRET": "${FIELD_SHARED_SECRET:-}",
    }
    # the image the command runs in installs the module it names
    dockerfile = (REPO / "integration" / "demo" / "Dockerfile").read_text(encoding="utf-8")
    assert "./packages/field-agent" in dockerfile.split("RUN pip install", 1)[1].split("\n\n", 1)[0]
    from field_agent import canary

    assert canary.DEFAULT_PORT == 8090 and callable(canary.main)


def test_a6_is_never_a_compose_or_fly_default_and_the_canary_manifest_names_the_service():
    base, gb10 = _compose("docker-compose.yml"), _compose("docker-compose.gb10.yml")["services"]
    assert base["x-service"]["environment"]["FIELD_KILL_ENDPOINT_ALLOWLIST"] == "${FIELD_KILL_ENDPOINT_ALLOWLIST:-}"
    assert gb10["sentinel"]["environment"]["FIELD_KILL_ENDPOINT_ALLOWLIST"] == "${FIELD_KILL_ENDPOINT_ALLOWLIST:-}"
    for name in ("docker-compose.yml", "docker-compose.gb10.yml"):
        raw = (REPO / "integration" / "demo" / name).read_text(encoding="utf-8")
        assert not re.search(r"FIELD_KILL_ENDPOINT_ALLOWLIST:-[^}]", raw), name
    # Fly: nothing until D7, and never loopback
    assert 'export FIELD_KILL_ENDPOINT_ALLOWLIST="${FIELD_KILL_ENDPOINT_ALLOWLIST:-}"' in _entrypoint()
    assert "canary-agent" not in _entrypoint()
    assert "./packages/field-agent" not in (FLY / "Dockerfile").read_text(encoding="utf-8")

    from field_core.manifest import FieldManifest
    from field_core.validation import load_manifest

    gb10_manifest = FieldManifest.from_dict(load_manifest(REPO / "manifests" / "canary-gb10.yaml"))
    assert gb10_manifest.enforcement.kill_switch.endpoint == "http://canary-agent:8090/halt"
    assert gb10_manifest.enforcement.kill_switch.method == "HTTP POST"
    fly_manifest = FieldManifest.from_dict(load_manifest(REPO / "manifests" / "canary-fly.yaml"))
    assert "canary-agent" not in fly_manifest.enforcement.kill_switch.endpoint


def test_the_runbook_arms_a6_scoped_runs_the_x3_check_and_disarms_allowlist_first():
    text = _runbook()
    step9 = _section(text, "9. **Bring v1.2 up", "10. **Copy the quiesced backup")
    assert "profile `x3`" in step9 and "FIELD_KILL_ENDPOINT_ALLOWLIST` stays unset" in step9
    x3 = _section(text, "### X3 halt endpoint (A6)", "### X4 witness (A5)")
    arm, disarm = x3[:x3.index("**Disarm, scoped")], x3[x3.index("**Disarm, scoped"):]
    assert "**Fly: nothing.** Never allowlist loopback there" in x3
    profile = arm.index("# BEFORE: must print nothing (profile not active)")
    switch = arm.index("COMPOSE_PROFILES=\\1,x3")
    assert profile < switch < arm.index('# AFTER: must print "canary-agent"') < arm.index(
        "$C up -d --no-deps --no-build canary-agent")
    allow = "printf '\\nFIELD_KILL_ENDPOINT_ALLOWLIST=canary-agent\\n' >> integration/demo/.env"
    assert arm.index("$C up -d --no-deps --no-build canary-agent") < arm.index(allow) < arm.index(
        "$C up -d --no-deps --no-build killswitch")
    check = "docker exec field-platform-killswitch-1 python -m field_agent.canary x3-check --agent canary-gb10"
    assert arm.index("$C up -d --no-deps --no-build killswitch") < arm.index(check)
    # disarm: the allowlist goes before the process, or every canary kill ledgers endpoint_failed
    assert disarm.index("FIELD_KILL_ENDPOINT_ALLOWLIST=canary-agent") < disarm.index(
        "$C up -d --no-deps --no-build killswitch") < disarm.index("$C stop canary-agent")
    assert "grep -x canary-agent` must print nothing" in disarm.replace("\n", " ")
