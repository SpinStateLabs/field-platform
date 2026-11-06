# Review PR #751 (sealed-ledger: retention_check, wrong-shaped registry answers, S7-26) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `9f0816b0ae28db74230c32f4add4f245a5f965c3`. This head is the follow-up to reviewer-6's PASS WITH CONDITIONS on `c8d1d00b` (comms/inbox/coordinator/20261105-1011-ssl-ff-reviewer-6-pr751-c8d1d00.md); I checked its condition and objections.

## Facts (HIGH, read from the head)
- 2 commits (c8d1d00b, 9f0816b0); 2 files: services/sealed-ledger/src/sealed_ledger/retention.py (+8/-1), tests/test_retention_check_shapes.py (new). Nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Tests: test_retention_check_shapes.py 26 passed on the head; with test_ledger_retention.py 62 passed, 1 failed (see below, not this PR).

## The change (retention.py `retention_check`)
- A list answer from the registry that holds a non-object (int, str, None, list) now raises TypeError("registry returned a list holding <sorted, de-duplicated type names>, not agent records"), so the check reports `registry unavailable: TypeError: ...` with type names only, never a value (before: AttributeError on `.get` made GET /retention/check a 500 and crashed the CLI).
- A `manifest_ref` is "no manifest declared" only when it is `None` or `""`; any other non-string value, truthy or falsy (`0`, `0.0`, `False`, `[]`, `{}`, a list, a dict, a number), is listed unresolvable with reason `invalid` and `manifest_ref` shown as `<typename>`, and never reaches the resolver. Whitespace-only strings still go to the resolver, as before.

## Reviewer-6's condition and objections, on this head
- Condition (a falsy non-string `manifest_ref` such as `False` was counted as "no manifest" and the check said ok): closed. `0`, `0.0`, `False`, `[]`, `{}` are now invalid (five parametrised tests plus "False never ok"); `None`, an absent key and `""` still count as without-manifest (pinned).
- Objection 2 (vacuous `"str" in detail` assertion, which let two survivors through): replaced by the exact detail `registry returned a list holding int, str, not agent records`; the only-first-type and not-sorted mutants are now killed.
- Objection 3 (older non-list check near-equivalent) and objection 4 (an `agent_id` copied unchanged from the registry record into the output): unchanged LOWs; the builder's note says so.

## Mutants (mine, 14 hand mutants on retention.py, one at a time against the shapes tests; clean run, file restored, tree clean afterwards). Counted from the output: 14 RED, 0 survived.
Falsy refs back to "no manifest"; only None counts as no manifest; only `""` counts as no manifest; non-string guard removed; odd-row check removed; only the first odd type named; types not sorted or de-duplicated; values echoed in the message; invalid ref echoed instead of its type; invalid reason text changed; invalid ref falls through to the resolver; None rows tolerated; odd-row error raised as ValueError; the empty-string branch made unreachable. (My first pass of this table was disturbed by an overlapping run of my own script, so I discarded it and re-ran the whole list; the equivalent pair "only None" and "None or (empty and False)" gave the same RED on re-run.)

## Not caused by this PR
`tests/test_ledger_retention.py::test_readers_during_rotate_and_real_retention_apply_never_see_a_short_ok_chain` fails on this Windows host with `archived_segments == 0` (assert `final.archived_segments > 0`), both on this head and on main `250154d3`; the chain-integrity assertions before it hold (ok chain, length equals acked). It is a timing-dependent archival expectation in a file this PR does not touch; I did not investigate it further.

## Conditions
None.

## Optional LOW (new PR only; head is frozen after this PASS)
1. `agent_id` (any JSON value) is passed into the unresolvable list unchanged (reviewer-6's objection 4); not tested.

## Not covered
The full sealed-ledger suite (only the retention files); Linux; did not rebase on current main.
