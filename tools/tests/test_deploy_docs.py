"""Static checks of the Phase C deploy configuration and runbook text.

Nothing here runs docker: the compose-upgrade-smoke job and the runbook's
docker commands are executed only by CI and by an operator. What can be
checked without docker is that the text says the right thing, and each check
below fails on the text an adversarial review found wrong (2026-09-13 fix
round):

- the CI job examines EVERY platform container for the read-only manifests
  mount, and every non-ledger one for the absence of the keys volume (INF-2);
- the job's non-manifest install control pins the refusal (exit 2 and the
  resolver's reason), not any non-zero exit (INF-10);
- the GB10 override mounts field-manifests read-only into every platform
  service and field-keys into the ledger only;
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
    assert {s for s, p, w in checked if (p, w) == ("/data/keys", "ro")} == {"ledger"}
    assert {s for s, p, w in checked if (p, w) == ("/data/keys", "absent")} == set(services) - {"ledger"}


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
