"""C-817 (reviewer C-765 on PR 345, F-C765-1): the top-level path carriers (a named volume's driver_opts device, a
secret's and a config's file) get the same text rule as the service keys: a non-string is a violation, never "allowed",
never a crash. The service-level half (volume source, env_file entry, build context and dockerfile, additional_contexts)
is pinned in test_compose_pr345_conditions_c715.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import test_compose_static_pins as pins  # noqa: E402

EMPTY = "services: {}\n"
BASE = "services:\n  s:\n    image: x\n"


def violations(extra: str):
    return pins.key_violations(BASE + extra, EMPTY)


@pytest.mark.parametrize("value", ["[/etc]", "5", "{a: 1}", "true"])
def test_a_non_string_volume_device_is_a_violation(value):
    out = violations(f"volumes:\n  v:\n    driver_opts:\n      device: {value}\n")
    assert any("driver_opts.device" in v and "not a string" in v for v in out), out


@pytest.mark.parametrize("section", ["secrets", "configs"])
@pytest.mark.parametrize("value", ["[/etc/shadow]", "5", "{a: 1}"])
def test_a_non_string_secret_or_config_file_is_a_violation(section, value):
    out = violations(f"{section}:\n  k:\n    file: {value}\n")
    assert any("file" in v and "not a string" in v for v in out), out


@pytest.mark.parametrize("extra", [
    "volumes:\n  v:\n    driver_opts:\n      device: /srv/data\n",
    "volumes:\n  v: {}\n",
    "volumes:\n  v:\n",
    "secrets:\n  k:\n    file: ./secret.txt\n",
    "configs:\n  k:\n    file: ./c.conf\n",
    "secrets:\n  k:\n    environment: HOME\n",
])
def test_string_and_absent_values_are_not_violations_of_this_rule(extra):
    out = violations(extra)
    assert not any("is not a string" in v or "shape this checker does not know" in v for v in out), out


@pytest.mark.parametrize("extra", ["volumes: 5\n", "secrets: [a]\n", "configs: 3\n", "volumes:\n  - a\n"])
def test_a_top_level_section_of_an_unknown_shape_is_a_violation_never_an_exception(extra):
    assert violations(extra)


def test_the_resolved_check_and_the_static_pins_agree_on_these_carriers():
    import compose_resolved_check as crc

    for doc in ({"services": {"s": {"image": "x"}}, "volumes": {"v": {"driver_opts": {"device": ["/etc"]}}}},
                {"services": {"s": {"image": "x"}}, "secrets": {"k": {"file": 5}}}):
        assert any("not a string" in line for line in crc.check_model(doc, "/srv-fixture/checkout"))


def test_the_docker_sock_assertion_is_kept_on_purpose_and_says_why():
    source = Path(pins.__file__).read_text(encoding="utf-8")
    assert "kept on purpose" in source and "RUNTIME_SOCKET" in source
