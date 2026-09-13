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
- no operator example puts a roster under /data/manifests (INF-5).

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
    assert wit["volumes"] == ["field-keys:/data/keys:ro"]  # no field-data: it writes through the served route
    assert "ports" not in wit and wit["restart"] == "unless-stopped" and wit["depends_on"] == ["ledger"]
    assert wit["environment"] == {
        "FIELD_LEDGER_URL": "http://ledger:8002",
        "FIELD_SHARED_SECRET": "${FIELD_SHARED_SECRET:-}",
        "FIELD_LEDGER_ANCHOR_KEY": "${FIELD_LEDGER_ANCHOR_KEY:-}",
        "FIELD_WITNESS_FLY_SECRET_FILE": "${FIELD_WITNESS_FLY_SECRET_FILE:-}",
    }
    # blank unless A5 sets it: an estate whose witness is not armed (or was disarmed) never gets
    # the finding; set, the sweep reads the same variable the witness command runs with
    assert gb10["lifecycle"]["environment"] == {"FIELD_WITNESS_EVERY": "${FIELD_WITNESS_EVERY:-}"}
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
