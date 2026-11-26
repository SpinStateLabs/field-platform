"""C-1147 (Don's ruling 2026-11-02 on PR 355 F-C847-1/-2): the NARROW rule for retired keys.

A key retired at ANY generation below the highest generation seen is refused when it is seen again AT that highest
generation. Same-generation re-reads of a file, and a rollback re-issued at a HIGHER generation, keep working.

Before the rule, the refusal test was ``generation <= retired[hash]`` only, so with generations 41, 42 and 43 rotating
a key A, then B, then C, the table held A at 42 and B at 43, and a second generation-43 file holding A was ACCEPTED
(reviewer C-889 objection 2, reproduced there with made-up keys). Every key below is an obviously fake test value."""
from __future__ import annotations

import copy
import json

import pytest

from field_core import operator_auth as oa

K_DON = "fok_test-don-current-not-a-real-key"
K_A = "fok_test-killswitch-gen41-not-a-real-key"
K_B = "fok_test-killswitch-gen42-not-a-real-key"
K_C = "fok_test-killswitch-gen43-not-a-real-key"
T0 = oa.parse_time("2026-11-20T03:00:00Z")


def h(key: str) -> str:
    return oa.key_sha256(key)


def ks_file(generation: int, key: str) -> dict:
    """A format 2 file: don (never changes) and svc-killswitch holding ``key`` as its only CURRENT key."""
    return {
        "format": 2, "generation": generation, "issued_at": "2026-11-20T03:12:09Z",
        "issued_by": "svc-rotator-gb10",
        "operators": [
            {"operator_id": "don", "status": "active", "scopes": ["*"], "names": ["Don Hagell"],
             "created_at": "2026-10-26T01:15:00Z", "rotation": "auto", "key_sha256": h(K_DON),
             "key_created_at": "2026-10-26T01:15:00Z", "key_not_after": "2027-01-09T01:15:00Z"},
            {"operator_id": "svc-killswitch", "status": "active", "scopes": ["kill", "revive", "drill"],
             "names": [], "event_prefixes": ["kill."], "created_at": "2026-10-26T01:15:00Z",
             "rotation": "auto", "key_sha256": h(key), "key_created_at": "2026-10-26T01:15:00Z",
             "key_not_after": "2027-01-09T01:15:00Z"},
        ]}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    monkeypatch.setattr(oa, "clock", lambda: T0)
    oa._reset_retired_memory()
    yield
    oa._reset_retired_memory()


@pytest.fixture()
def enforce_file(tmp_path, monkeypatch):
    p = tmp_path / "operators.json"

    def write(d):
        p.write_text(json.dumps(copy.deepcopy(d)), encoding="utf-8")
        return p

    write(ks_file(41, K_A))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    return write


def _headers(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


def ok(op, key):
    return oa.authenticate(_headers(op, key), "kill").authenticated


def refused(op, key):
    """ENFORCE mode raises on a refusal; a retired key is a 403 alone, never a 503."""
    with pytest.raises(oa.OperatorRefused) as exc:
        oa.authenticate(_headers(op, key), "kill")
    assert exc.value.status == 403


def rotate_a_b_c(enforce_file):
    """Generations 41, 42 and 43 rotate svc-killswitch A, then B, then C. The table now holds A at 42, B at 43."""
    enforce_file(ks_file(41, K_A))
    assert ok("svc-killswitch", K_A)
    enforce_file(ks_file(42, K_B))
    assert ok("svc-killswitch", K_B)
    enforce_file(ks_file(43, K_C))
    assert ok("svc-killswitch", K_C)


def test_a_key_retired_below_the_high_generation_is_refused_at_the_high_generation(enforce_file):
    rotate_a_b_c(enforce_file)
    enforce_file(ks_file(43, K_A))                         # A was retired at 42; 43 is the highest generation seen
    refused("svc-killswitch", K_A)
    assert ok("don", K_DON)                                # the rest of the file still works (403 alone, never 503)
    assert oa.retired_hash_seen == 1


def test_a_key_retired_at_the_high_generation_is_still_refused_there(enforce_file):
    """The case that was already refused (``generation <= retired[hash]``): B was retired at 43."""
    rotate_a_b_c(enforce_file)
    enforce_file(ks_file(43, K_B))
    refused("svc-killswitch", K_B)
    assert ok("don", K_DON)


def test_the_same_generation_file_read_again_is_accepted(enforce_file):
    rotate_a_b_c(enforce_file)
    enforce_file(ks_file(43, K_C))                         # the very file already loaded, read again
    assert ok("svc-killswitch", K_C)
    assert ok("svc-killswitch", K_C)
    assert ok("don", K_DON)
    assert oa.retired_hash_seen == 0


def test_a_rollback_re_issued_at_a_higher_generation_is_accepted(enforce_file):
    rotate_a_b_c(enforce_file)
    enforce_file(ks_file(44, K_A))                         # A comes back as a NEW issue above the high generation
    assert ok("svc-killswitch", K_A)
    assert oa.retired_hash_seen == 0


def test_a_re_issued_key_survives_a_re_read_of_its_own_generation(enforce_file):
    """The re-issue at 44 clears A from the retired table; reading generation 44 again must not refuse it as a
    'retired key seen at the high generation' (the narrow rule must not turn a re-issue into a refusal)."""
    rotate_a_b_c(enforce_file)
    enforce_file(ks_file(44, K_A))
    assert ok("svc-killswitch", K_A)
    enforce_file(ks_file(44, K_A))
    assert ok("svc-killswitch", K_A)
    assert oa.retired_hash_seen == 0


def test_the_re_issued_key_is_refused_again_once_it_is_retired_again(enforce_file):
    rotate_a_b_c(enforce_file)
    enforce_file(ks_file(44, K_A))
    assert ok("svc-killswitch", K_A)
    enforce_file(ks_file(45, K_B))                         # A retired again, at 45
    assert ok("svc-killswitch", K_B)
    enforce_file(ks_file(45, K_A))                         # and seen again at the high generation
    refused("svc-killswitch", K_A)


def test_a_key_retired_below_is_refused_in_a_lower_generation_file_too(enforce_file):
    """Unchanged behaviour next to the new rule: A is refused in a generation 42 or 41 file."""
    rotate_a_b_c(enforce_file)
    enforce_file(ks_file(42, K_A))
    refused("svc-killswitch", K_A)
    enforce_file(ks_file(41, K_A))
    refused("svc-killswitch", K_A)


def test_the_first_load_of_a_file_refuses_nothing(enforce_file):
    """No memory yet (a restart forgets: Declared in operator_auth.py): the narrow rule needs a high generation."""
    enforce_file(ks_file(43, K_A))
    assert ok("svc-killswitch", K_A)
    assert oa.retired_hash_seen == 0
