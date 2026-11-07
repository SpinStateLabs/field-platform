# Delta review PR 699 (S5-21 force-gateway real_upstream named 502) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS WITH CONDITIONS** on head `47cdb26bc0184b6d74f981e9af46d36a5ef64856`. It is the head I reviewed (1b14b68b) plus a merge of current origin/main ccd013d4: my C1 (rebase and refresh docs/ENVIRONMENT.md; the trial merge conflicted) is CLOSED. The one open condition is the standing gate.
Conditions: C1 (standing gate) CI and GX10 on this exact head (Linux not verified); not run by me.

Independence: I did not build or fix this PR (5 commits, none mine; the merge is builder-6's per its note). I reviewed 1b14b68b earlier as a reviewer, which does not make me an author.

## Checks (HIGH, run by me)
- Identity: 5 of 5 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Shape: the second parent of the head is current origin/main ccd013d4f (not behind); `git merge-tree` against origin/main is clean (tree id only). Diff vs main: docs/ENVIRONMENT.md +/-20, api.py +/-34, test_real_upstream_transport.py +185 (3 files, +218/-21).
- Code unchanged: `git patch-id --stable` of the force-gateway part of the PR diff is identical at 1b14b68b and at this head (both 1d65bd66c9a9), so api.py and the tests are exactly what I reviewed.
- `environment_anchors.py --check`: 0 wrong anchor row(s); `test_environment_doc.py` 62 passed.
- Tests on the exact head (Windows, py3.14, venv): `test_real_upstream_transport.py` 39 passed (19 s).

## Mutants (3 re-run on this head, one at a time, file restored and tree verified clean; counted from the table)
| # | mutant (api.py) | result |
|---|---|---|
| M1 | transport raise: `from None` -> `from exc` | KILLED |
| M2 | non-object raise: `from None` dropped | KILLED |
| M3 | the non-dict guard removed | KILLED |
Totals: 3 attempted, 3 killed, 0 survived, 0 not applied. My four mutants on 1b14b68b (M1 to M4, all killed) apply unchanged to identical code.

## Not verified
CI; GX10; Linux; the whole force-gateway suite on this head; the pre-existing raw `ValueError: Invalid IPv6 URL` path reviewer-7 noted (outside this PR).
