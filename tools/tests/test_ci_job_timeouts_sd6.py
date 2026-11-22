"""Every ci.yml job sets timeout-minutes (GitHub's default is 360, so a hung
step would hold a runner for six hours). Measured on GitHub (run 41795375468): tests 17-20 min,
compose jobs 2-3 min, fly-image-smoke 2 min; the caps leave headroom and stay
well under an hour."""

from pathlib import Path

import yaml

CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
CAPS = {"tests": 45, "compose-smoke": 20, "fly-image-smoke": 30,
        "compose-upgrade-smoke": 20}


def _jobs():
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


def test_every_job_has_a_bounded_timeout():
    jobs = _jobs()
    assert set(jobs) == set(CAPS), "new or removed job: set its cap here too"
    for name, job in jobs.items():
        t = job.get("timeout-minutes")
        assert type(t) is int and 0 < t <= 60, (name, t)


def test_caps_are_the_documented_values():
    assert {n: j["timeout-minutes"] for n, j in _jobs().items()} == CAPS
