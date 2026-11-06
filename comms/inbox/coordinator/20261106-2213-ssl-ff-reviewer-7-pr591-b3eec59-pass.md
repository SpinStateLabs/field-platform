# Review PR 591 (scout S-2-8: federation-broker tests for home_org() and the blank FIELD_ORG_NAME behaviour) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `b3eec590688df60a39db95055894e0aad0d0595f` (tests only, no source change; no conditions beyond the standard CI on the landed head).

## Checks (HIGH, run by me)
- Identity: 2 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5 (the first commit shows none); .github/: 0 files. One new file: services/federation-broker/tests/test_home_org.py (+147). Based on 97dcfec1; main is 250154d3; a trial merge into current main is clean.
- Content checked against the code (engine.py): `home_org()` is `os.environ.get("FIELD_ORG_NAME", "Spin State Labs")` with no normalisation; `_lists_org` normalises the needle and returns False when it is empty, so a blank home org makes every inbound crossing BLOCK at `F.peer` with the reason "counterparty manifest does not list  as an allowed peer" (an empty name, a double space): the tests pin each of those as the code behaves today, including the card correction (a whitespace-only value is returned verbatim, not collapsed to the empty string).
- Tests on the exact head (Windows): test_home_org.py 36 passed (the PR said 26: the second commit added the padded-value `/health` cases); the PR also reports the whole suite 217 passed (not re-run by me).
- The recommendation in the PR body (do not fall back to the default on a blank value; surface it through a `/health` field and a startup warning; name the setting in the verdict text) is sound on the merits: a blank today fails closed for inbound but the service keeps running with an unnamed org. It needs Don's decision and is not in this PR.

## Mutants (10 on engine.py vs test_home_org.py; counted from the table)
| # | mutant | result |
|---|---|---|
| H1 | a blank value falls back to the default | KILLED |
| H2 | value stripped | KILLED |
| H3 | default changed | KILLED |
| H4 | env variable renamed | KILLED |
| H5 | value lower-cased | KILLED |
| L1 | empty-needle guard removed | KILLED |
| L2 | guard on the raw org instead of the normalised needle | KILLED |
| L3 | non-list peers accepted | KILLED |
| P1 | F.peer reason uses a fixed word instead of the home org | KILLED |
| P2 | F.peer clause id changed | KILLED |
Totals: 10 mutants, 10 killed, 0 survived.

## Not verified
CI/GX10; Linux; the PR's whole-suite count; that `test_http_env_proxy_lint_c57` is red on main (the PR says so; not checked).
