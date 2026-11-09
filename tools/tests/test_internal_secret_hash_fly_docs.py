"""R-PR867-37e5926 C1: after PR 867 the Fly entrypoint exports FIELD_INTERNAL_SECRET_SHA256 to every process, so the Stage 2
runbook step and the ENVIRONMENT.md row must say so and name the Fly way to set it (`fly secrets set`), not still say the
entrypoint does not yet pass it, and must warn that a malformed value stops every process on the machine."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = " ".join((ROOT / "docs/runbooks/v1.2-deploy-rollback.md").read_text(encoding="utf-8").split())
ENV_ROW = next(line for line in (ROOT / "docs/ENVIRONMENT.md").read_text(encoding="utf-8").splitlines()
               if line.startswith("| `FIELD_INTERNAL_SECRET_SHA256`"))
ENTRYPOINT = (ROOT / "integration/fly/entrypoint.sh").read_text(encoding="utf-8")


def test_the_entrypoint_does_export_the_hash():
    assert 'export FIELD_INTERNAL_SECRET_SHA256="${FIELD_INTERNAL_SECRET_SHA256:-}"' in ENTRYPOINT


def test_the_runbook_no_longer_says_the_fly_entrypoint_does_not_pass_it():
    assert "the Fly entrypoint does not yet" not in RUNBOOK


def test_the_runbook_names_the_fly_way_and_the_malformed_value_consequence():
    step = RUNBOOK.split("COORDINATOR AT GO-POINT (not code): the secret file exists", 1)[1].split("(f) v1 is a static secret", 1)[0]
    assert "fly secrets set FIELD_INTERNAL_SECRET_SHA256" in step
    assert "integration/fly/entrypoint.sh" in step and "every process" in step
    assert "stops every process" in step


def test_the_environment_row_names_the_fly_way_and_the_malformed_value_consequence():
    assert "fly secrets set FIELD_INTERNAL_SECRET_SHA256" in ENV_ROW
    assert "integration/fly/entrypoint.sh" in ENV_ROW and "whole machine" in ENV_ROW
