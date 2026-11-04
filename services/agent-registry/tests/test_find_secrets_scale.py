"""S7-14: find_secrets and scan_secrets_text were quadratic in the number of hits.

`find_secrets` tested every candidate span against a flat list of every earlier accepted span, and `scan_secrets_text`
counted newlines from offset 0 for every hit. Measured before the fix (this machine, one 25-byte stripe-style key per
line): 5,000 hits 1.1 s, 10,000 hits 4.1 s, 20,000 hits 17.7 s in find_secrets, 31.3 s in scan_secrets_text; the 1 MiB cap
admits about 41,000. After: 41,000 hits 0.5 s and 1.0 s. The OLD algorithms are copied below as the oracle: the result list,
its order and the first-pattern-claims-the-span rule must be byte-identical."""

import random
import string
import time

import pytest

from agent_registry.discover import scan_secrets_text
from agent_registry.models import SecretHit
from agent_registry.redaction import KEY_PATTERNS, VERY_BROAD_PATTERN, RawHit, find_secrets


def old_find_secrets(text, *, include_very_broad, bounded=True):
    patterns = KEY_PATTERNS + ((VERY_BROAD_PATTERN,) if include_very_broad else ())
    taken, hits = [], []
    for pattern in patterns:
        regex = pattern.regex if bounded else pattern.loose
        for m in regex.finditer(text):
            start, end = m.span(pattern.group)
            if any(start < t_end and t_start < end for t_start, t_end in taken):
                continue
            taken.append((start, end))
            hits.append(RawHit(pattern.name, pattern.breadth, m.group(pattern.group), start, end))
    hits.sort(key=lambda h: h.start)
    return hits


def old_scan_secrets_text(text, include_very_broad=False):
    return [SecretHit(pattern=h.pattern, breadth=h.breadth, value=h.value, line=text.count("\n", 0, h.start) + 1)
            for h in old_find_secrets(text, include_very_broad=include_very_broad)]


FRAGMENTS = [
    "sk-ant-" + "a" * 40, "sk-" + "B" * 30, "sk-proj-" + "c" * 25, "AIza" + "d" * 35, "hf_" + "e" * 31,
    "AKIA" + "F" * 16, "ghp_" + "g" * 40, "xoxb-" + "1" * 12, "sk_live_" + "h" * 20, "sk_test_" + "i" * 16,
    "ya29." + "j" * 22, "eyJ" + "k" * 10 + ".eyJ" + "l" * 10 + "." + "m" * 10, "api_key = " + "n" * 14,
    "secret=\"" + "o" * 13 + "\"", "token = 'x'", "\n", " ", "prod", "wf-", "-", "_", "plain text", "sk-ant-short",
]


def random_text(rng, parts):
    return "".join(rng.choice(FRAGMENTS) if rng.random() < 0.8 else rng.choice(string.printable) for _ in range(parts))


def test_new_find_secrets_equals_the_old_algorithm_on_200_random_strings_and_the_fragment_corpus():
    rng = random.Random(20261104)
    corpus = list(FRAGMENTS) + [" ".join(FRAGMENTS), "".join(FRAGMENTS), "\n".join(FRAGMENTS)]
    corpus += [random_text(rng, rng.randint(1, 40)) for _ in range(200)]
    for text in corpus:
        for very_broad in (False, True):
            for bounded in (True, False):
                assert find_secrets(text, include_very_broad=very_broad, bounded=bounded) == \
                    old_find_secrets(text, include_very_broad=very_broad, bounded=bounded), (text, very_broad, bounded)


def test_overlapping_matches_keep_the_first_pattern_in_order_and_the_text_order():
    # an sk-ant key is also a broad sk- key: the first pattern in KEY_PATTERNS order claims the span
    text = "x sk-ant-" + "a" * 40 + "\n" + "AKIA" + "Z" * 16
    hits = find_secrets(text, include_very_broad=False)
    assert [h.pattern for h in hits] == ["anthropic", "aws-access-key-id"]
    assert hits == old_find_secrets(text, include_very_broad=False)


def test_new_scan_secrets_text_gives_the_same_line_numbers_as_the_old_per_hit_count():
    rng = random.Random(7)
    for _ in range(100):
        text = random_text(rng, rng.randint(1, 60))
        assert scan_secrets_text(text, include_very_broad=True) == old_scan_secrets_text(text, include_very_broad=True)
    text = "line one\n\nsk-ant-" + "a" * 40 + "\nx\nAKIA" + "Q" * 16 + "\n"
    assert [h.line for h in scan_secrets_text(text)] == [3, 5]


def _body(n):
    rng = random.Random(1)
    return "\n".join("sk_live_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(16))
                     for _ in range(n))


def test_forty_thousand_adjacent_keys_under_the_cap_scan_in_bounded_time():
    body = _body(40_000)
    assert len(body.encode()) < 1024 * 1024
    t0 = time.perf_counter()
    hits = scan_secrets_text(body)
    elapsed = time.perf_counter() - t0
    assert len(hits) == 40_000 and hits[0].line == 1 and hits[-1].line == 40_000
    # about 1 s here; the old code took over a minute. A generous bound so a slow CI box does not flake.
    assert elapsed < 10, f"{elapsed:.1f}s for 40,000 hits"
