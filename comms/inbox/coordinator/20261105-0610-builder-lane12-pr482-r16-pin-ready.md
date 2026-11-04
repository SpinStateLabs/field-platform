builder Lane 12: PR 482 (C-1205), head 198afb112a08489a9487dacff9c74b8bd091254d, Lane 15 Q-130 PASS, GX10 B 16 of 16. I do NOT push to the head (head-freeze). F-Q130-1 (LOW, R16) is real; here is the verified pin.

Verified locally on the PR branch (relative PYTHONPATH, one test file, then restored):
- real R16 = replace the whole guard `if estate is not None and days > estate:` with `if days > (estate or 0):` in sealed_ledger/retention.py.
- the original 40 tests: 40 passed under R16 (the mutant survives, as Lane 15 measured).
- the 40 plus the test below: R16 makes exactly that one test fail; on the unmutated source 41 passed.
- Note: a first attempt of mine used a weaker mutant that kept the `estate is not None and` guard; that one is equivalent and the pin cannot kill it. R16 must replace the guard.

The test, to be appended at the end of services/sealed-ledger/tests/test_filters_retention_direct_c1205.py (uses the file's own _manifests, _Store, _Registry, _agent, GOOD_STATE, RETENTION_ENV):

def test_without_a_usable_estate_policy_no_manifest_is_listed_as_offending(monkeypatch):
    # F-Q130-1 (Lane 15): kills ``days > estate`` -> ``days > (estate or 0)``, which would list every manifest as
    # offending while the status says there is no policy to offend.
    _manifests(monkeypatch, {"big": 2555})
    for policy in (None, "abc", "0"):
        if policy is None:
            monkeypatch.delenv(RETENTION_ENV, raising=False)
        else:
            monkeypatch.setenv(RETENTION_ENV, policy)
        out = retention_check(_Store(GOOD_STATE), _Registry([_agent("a", "big")]))
        assert out.status == "no_estate_policy" and out.ok is False, policy
        assert out.offending == [] and out.manifests_checked == 1 and out.max_manifest_retention_days == 2555, policy

Options: (a) the coordinator appends it in the batch commit (cheapest; no gate resets); (b) a follow-up PR after 482 lands (the file does not exist on main until then); (c) tell me and I push it to 482 (resets the PASS and the 19.5 minute GX10 run). I will not push without your word. It is LOW and optional. Read, not measured.
