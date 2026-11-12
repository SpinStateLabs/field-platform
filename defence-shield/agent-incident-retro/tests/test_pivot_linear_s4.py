"""S.pivot answers each payload request from an index, not a window scan (S4 B6).

The reference below is the previous quadratic implementation, kept verbatim so the
new one is checked against it on random sessions (same hit, detail and cited lines).
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
            shared = [k for k in tampered if k in b_vals and b_vals[k] != r_vals.get(k)]
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
            if rnd.random() < 0.35:
                q = f"{rnd.choice(['q', 'id'])}={rnd.choice(PAYLOADS)}"
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
