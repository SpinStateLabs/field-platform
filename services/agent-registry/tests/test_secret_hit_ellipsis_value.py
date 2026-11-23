"""B-S11-9: a credential-shaped value containing U+2026 must not crash SecretHit construction."""

import pytest

from agent_registry import redaction
from agent_registry.models import SecretHit
from agent_registry.redaction import fingerprint, redact, redact_text

E=chr(0x2026)


@pytest.mark.parametrize("n", [11, 12, 21, 22, 23])
def test_redact_shape_at_boundary_lengths(n):
    out = redact("abcdefghijklmnopqrstuvwxyz"[:n])
    assert out.count(E) == 1 and len(out) - 1 <= 11


@pytest.mark.parametrize("value", [
    "token" + E + "abcdefghijkl",            # ellipsis inside the revealed prefix (len 17)
    E * 12,                                  # all ellipses, short branch
    "abcdefg" + E * 8 + "wxyz" + E * 3,      # long branch, ellipsis in prefix and tail
    "ab" + E + "cdefghijklmnopqrstuvw" + E + "xyz",
])
def test_redact_total_and_never_a_whole_value(value):
    out = redact(value)
    assert out.count(E) == 1 and len(out) - 1 <= 11
    assert len(value) > 11  # redaction is strictly shorter than the value


@pytest.mark.parametrize("value", [
    "token" + E + "abcdefghijkl",
    "secret=" + E + "abcdefghijklmnop" + E,
    E * 30,
])
def test_secrethit_construction_total_over_ellipsis_values(value):
    hit = SecretHit(pattern="assignment", breadth="very-broad", line=1, value=value)
    assert hit.redacted.count(E) == 1
    assert hit.length == len(value)
    assert hit.fingerprint == fingerprint(value)


def test_redact_text_mixed_string_with_ellipsis_secret():
    text = "x token=" + E + "abcdefghijklmnop" + E + " and sk-" + "A" * 24 + " end"
    out = redact_text(text)
    assert out.count("[REDACTED") == 2
    assert "A" * 24 not in out
