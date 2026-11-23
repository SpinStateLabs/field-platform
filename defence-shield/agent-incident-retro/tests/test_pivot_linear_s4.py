"""S.pivot answers each payload request from an index, not a window scan (S4 B6).

The reference below is the previous quadratic implementation, kept verbatim so the
new one is checked against it on random sessions (same hit, detail and cited lines),
except its tamper test, which is S10-31's (every value of a repeated name is kept: a hit
when any value of the name in the payload request is absent from all the benign ones).
"""

import random
from collections import defaultdict

from agent_incident_retro.clauses import _hit, s_pivot
from agent_incident_retro.signatures import hostile_params, param_values
from test_clauses import req, sess

PAYLOADS = ["%27%20OR%20%271%27%3D%271", "%3Cscript%3Ealert(1)%3C%2Fscript%3E", "..%2F..%2Fetc%2Fpasswd"]


def _reference(s, window_s):
    refs, pairs = [], 0
    benign_by_path = defaultdict(list)
    for r in s.requests:
        if not r.is_hostile:
            benign_by_path[r.path].append(r)
            continue
        if not r.is_payload:
            continue
        tampered = hostile_params(r.query)
        if not tampered:
            continue
        r_vals = param_values(r.query)
        for b in reversed(benign_by_path.get(r.path, [])):
            if (r.ts - b.ts).total_seconds() > window_s:
                break
            b_vals = param_values(b.query)
            shared = [k for k in tampered
                      if k in b_vals and any(v not in b_vals[k] for v in r_vals.get(k, ()))]
            if shared:
                refs.extend([b.ref, r.ref])
                pairs += 1
                break
    return pairs, refs


def test_pivot_matches_the_quadratic_reference_on_random_sessions():
    rnd = random.Random(20261112)
    fired = 0
    for _ in range(400):
        reqs, t = [], 0
        for n in range(1, rnd.randint(2, 40)):
            t += rnd.choice([0, 1, 5, 60, 200, 400])
            path = rnd.choice(["/a", "/b"])
            roll = rnd.random()
            if roll < 0.2:
                q = f"{rnd.choice(['q', 'id'])}={rnd.choice(PAYLOADS)}"
            elif roll < 0.35:  # repeated key: every value is kept (S10-31); one of them may be benign
                k = rnd.choice(["q", "id"])
                q = f"{k}={rnd.choice(PAYLOADS)}&{k}={rnd.choice(['x', 'y'])}"
            else:
                q = "&".join(f"{k}={rnd.choice(['x', 'y', 'z'])}" for k in rnd.sample(["q", "id", "p"], rnd.randint(0, 2)))
            reqs.append(req(n, t, path, q))
        s = sess(reqs)
        want_pairs, want_refs = _reference(s, 300.0)
        got = s_pivot(s, 300.0)
        assert (got is not None) == (want_pairs > 0)
        if got:
            fired += 1
            detail = f"{want_pairs} benign\u2192tampered pivot(s) on the same path and parameter within 300 s"
            assert got == _hit("S.pivot", detail, want_refs)
    assert fired > 20


def test_pivot_with_many_benign_requests_is_not_quadratic():
    reqs = [req(n, n % 250, "/search", "q=same") for n in range(1, 6001)]
    reqs.append(req(6001, 250, "/search", "q=%27%20OR%20%271%27%3D%271"))
    reqs.sort(key=lambda r: r.ts)
    assert s_pivot(sess(reqs), 300.0) is not None


def _same(reqs, window=300.0):
    s = sess(reqs)
    want_pairs, want_refs = _reference(s, window)
    got = s_pivot(s, window)
    assert (got is not None) == (want_pairs > 0)
    if got:
        detail = f"{want_pairs} benign\u2192tampered pivot(s) on the same path and parameter within {window:.0f} s"
        assert got == _hit("S.pivot", detail, want_refs)
    return got


SQLI = "%27%20OR%20%271%27%3D%271"


def test_pivot_edge_cases_match_the_reference():
    # window boundary: exactly the window fires, one second more does not
    assert _same([req(1, 0, "/s", "q=books"), req(2, 300, "/s", f"q={SQLI}")]) is not None
    assert _same([req(1, 0, "/s", "q=books"), req(2, 301, "/s", f"q={SQLI}")]) is None
    # a benign value equal to the payload value is not a pivot; an older different one is
    assert _same([req(1, 0, "/s", "q=books"), req(2, 10, "/s", f"q={SQLI}"), req(3, 20, "/s", "q=books")]) is not None
    # newest benign use with the same value as the payload is skipped for an older, different one
    assert _same([req(1, 0, "/s", "q=a"), req(2, 5, "/s", "q=b"), req(3, 6, "/s", "q=b"), req(4, 30, "/s", f"q={SQLI}")]) is not None
    # two tampered parameters: the newest matching benign request is the one cited
    two = f"q={SQLI}&id={SQLI}"
    got = _same([req(1, 0, "/s", "q=a"), req(2, 5, "/s", "id=b"), req(3, 30, "/s", two)])
    assert got is not None and [r.line for r in got.lines] == [2, 3]
    got = _same([req(1, 0, "/s", "id=b"), req(2, 5, "/s", "q=a"), req(3, 30, "/s", two)])
    assert [r.line for r in got.lines] == [2, 3]
    # duplicate keys: every value is kept on both sides (S10-31)
    assert _same([req(1, 0, "/s", "q=a&q=b"), req(2, 9, "/s", f"q={SQLI}")]) is not None


def test_pivot_work_does_not_grow_with_the_benign_run(monkeypatch):
    import agent_incident_retro.clauses as c

    calls = {"n": 0}
    real = c.param_values

    def counting(q):
        calls["n"] += 1
        return real(q)

    monkeypatch.setattr(c, "param_values", counting)
    reqs = [req(n, n % 250, "/search", f"q={'a' if n % 2 else 'b'}") for n in range(1, 2001)]
    reqs += [req(2001 + i, 250, "/search", f"q={SQLI}") for i in range(50)]
    reqs.sort(key=lambda r: r.ts)
    assert s_pivot(sess(reqs), 300.0) is not None
    assert calls["n"] <= 2 * len(reqs)  # the old scan re-parsed benign queries per payload request


def test_pivot_repeated_key_carrying_a_benign_value_too_is_a_pivot():
    # S10-31 (ruling on the rebuild of PR 964): `q=<payload>&q=safe` against a benign `q=safe` IS a pivot. Before, the
    # last value won, so the payload request looked unchanged and this asserted None.
    got = _same([req(1, 0, "/s", "q=safe"), req(2, 10, "/s", f"q={SQLI}&q=safe")])
    assert got is not None and [r.line for r in got.lines] == [1, 2]
    # the newest benign use is the one cited now (its values lack the payload), no longer an older different one
    got = _same([req(1, 0, "/s", "q=other"), req(2, 5, "/s", "q=safe"), req(3, 10, "/s", f"q={SQLI}&q=safe")])
    assert got is not None and [r.line for r in got.lines] == [2, 3]


def test_s10_31_benign_cat_then_payload_and_cat_fires():
    got = _same([req(1, 0, "/s", "q=cat"), req(2, 30, "/s", f"q={SQLI}&q=cat")])
    assert got is not None and [r.line for r in got.lines] == [1, 2]


def test_a_reordered_repeat_with_the_payload_elsewhere_does_not_fire_on_q():
    # the payload is in p, which no benign request used; q only repeats the benign values in another order
    assert _same([req(1, 0, "/s", "q=a&q=b"), req(2, 30, "/s", f"q=b&q=a&p={SQLI}")]) is None


def test_a_changed_benign_parameter_is_not_a_pivot_when_the_payload_is_in_another_name():
    # R-PR1158 C1 (roley.reviewer M7): q changes a -> b, but q carries no payload; the payload is in z, which no benign
    # request used, so there is no pivot (only a TAMPERED name with a benign use counts)
    assert _same([req(1, 0, "/s", "q=a"), req(2, 30, "/s", f"q=b&z={SQLI}")]) is None


def test_an_unchanged_repeated_benign_value_set_cites_the_newest_use():
    import agent_incident_retro.clauses as c

    reqs = [req(1, 0, "/s", "q=a&q=b"), req(2, 10, "/s", "q=a&q=b"), req(3, 30, "/s", f"q={SQLI}&q=a")]
    got = _same(reqs)
    assert got is not None and [r.line for r in got.lines] == [2, 3]
    # the index keeps the latest benign use per (path, name); every value of a repeated name is kept
    assert c.param_values("q=a&q=b") == {"q": ["a", "b"]}


def test_pivot_value_comparisons_do_not_grow_with_benign_times_payload_repeats(monkeypatch):
    """don.reviewer C1 on the rebuild of PR 964: a benign request and a payload request each repeating one name N times
    must not cost N x N value comparisons (a list scan per payload value); the benign values are a set. A work count,
    not a wall clock: every value is a str subclass that counts its == calls."""
    import agent_incident_retro.clauses as c

    eq_calls = {"n": 0}

    class Counted(str):
        __hash__ = str.__hash__

        def __eq__(self, other):
            eq_calls["n"] += 1
            return str.__eq__(self, other)

    real = c.param_values
    monkeypatch.setattr(c, "param_values", lambda q: {k: [Counted(v) for v in vs] for k, vs in real(q).items()})
    n = 2000
    benign = req(1, 0, "/s", "&".join(f"q=v{i}" for i in range(n)))
    # every benign value first, the payload last: a list scan finds each of them after i comparisons
    payload = req(2, 10, "/s", "&".join([f"q=v{i}" for i in range(n)] + [f"q={SQLI}"]))
    assert s_pivot(sess([benign, payload]), 300.0) is not None
    assert eq_calls["n"] <= 10 * n, eq_calls["n"]  # the list scan made about n * n / 2 (2 000 000) comparisons
