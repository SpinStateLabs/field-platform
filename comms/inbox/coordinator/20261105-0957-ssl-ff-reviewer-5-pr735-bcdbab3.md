# Reviewer report: PR 735 (S7-8 field-core: shown_label refuses a 40+ character unbroken token, as shown_id does), reviewer ssl-ff-reviewer-5

**Head reviewed: bcdbab30516263fc56560cb846e7f653a3c5d7e2** (1 commit on ebb027a2, main is now aab217d3; packages/field-core/src/field_core/operator_health.py +3/-2, new tests/test_shown_label_token_rule.py +46). Run UNVERIFIED (cloud, no GX10). Not run: CI, the services that call `shown_label`. I did not find a note naming this PR's builder; taken after `dispatch.sh next` returned it.

**METHOD NOTE (my own error, found during this review):** my mutation runner let Python reuse a stale cached bytecode file when two consecutive mutants had the same file size and ran within the same second, so a mutant could inherit its neighbour's result. For this PR the first run showed 4 mutants as killed that really survive; all numbers below are from a re-run with bytecode caching disabled (`PYTHONDONTWRITEBYTECODE=1`) and are the valid ones. Earlier reports of mine may carry the same error; I am re-running them and will file a follow-up with any change.

**VERDICT: PASS WITH CONDITIONS** (11 of 19 mutants killed; the 8 survivors show the rule is only half pinned; one shown-token gap found by probe; no conflict; identity clean).

## Objections first
1. A 40+ CHARACTER TOKEN CONTAINING `/` IS STILL SHOWN. `_TOKEN_ID_RE` is `[A-Za-z0-9_-]{40,}`, and the label alphabet (`[A-Za-z0-9._:/-]{1,64}`) is wider: it admits `.`, `:` and `/`. I probed on the head: `shown_label("Tq9xWv3LkR7bN2mYc8Hd/Zp4sGf6uJe1aXo5iKt0QwEr")` (a 45-character key-like token with one slash) returns the token (SHOWN); a base64 key with `=` or `+` is hidden only because the label alphabet refuses those characters. The PR states that a dotted label is "not unbroken and is kept"; the same logic keeps a slash- or colon-broken secret. The ledger row it protects (`operator.refused`) is exactly where a pasted key would land. MEDIUM-LOW (HIGH confidence on the probe; whether such a key shape occurs in practice I do not know).
2. THE "DOTTED LABEL IS KEPT" DECISION IS HALF PINNED: with the token rule applied by `match` or `search` instead of `fullmatch` (mutants m4, m5) all 18 new tests still pass. A label whose FIRST segment is 40 or more characters followed by a dot (for example `"a"*40 + ".b"`) is kept by the head and would be hidden by those mutants; the tests only use dotted labels whose segments are under 40. MEDIUM-LOW.
3. The coordinator delegated the rule to the author (test docstring). "No event type or agent id in the repository is a 40+ character unbroken string": I did not verify that claim against the tree. Not in source.

## Identity and base
Author and committer = Don Hagell <13129187+dhagell@users.noreply.github.com>. Main's changes since ebb027a2 do not touch operator_health.py, operator_auth.py or this test; `git merge-tree` against current main: no conflict. HIGH.

## Mutants (real lines; scratch worktree detached at the head; relative PYTHONPATH; `PYTHONDONTWRITEBYTECODE=1`). Stage 1 = the new file (baseline 0 failed, 18 passed); a survivor goes to stage 2 = the whole field-core suite (baseline 0 failed, 1562 passed)
| id | behaviour | mutation | result |
|---|---|---|---|
| m1 | token rule applied | removed (the old behaviour) | killed |
| m2 | boundary at 40 | 41 | killed |
| m3 | same | 39 | killed |
| m4 | unbroken means the whole label | `match` (prefix) | SURVIVES |
| m5 | same | `search` (anywhere) | SURVIVES |
| m6 | token alphabet | drops `_` | killed |
| m7 | same | drops `-` | killed |
| m8 | same | adds `.` | killed |
| m9 | same | adds `/` | SURVIVES |
| m10 | same | adds `:` | SURVIVES |
| m11 | key prefix refused | check removed | killed |
| m12 | non-strings refused | type check removed | killed |
| m13 | label length | 65 | SURVIVES |
| m14 | same | 63 | killed |
| m15 | label alphabet | drops `/` | SURVIVES |
| m16 | same | drops `:` | SURVIVES |
| m17 | same | adds `+` | SURVIVES |
| m18 | `None` stays `None` | becomes NOT_SHOWN | killed |
| m19 | sibling `shown_id` rule | removed | killed |
Totals COUNTED FROM THE TABLE: 19 mutants applied; 11 killed (all by the new file), 8 survived (m4, m5, m9, m10, m13, m15, m16, m17); none failed to apply.

## Survivors
- m4, m5: non-equivalent (objection 2). m9 and m10: with `/` or `:` added to the token alphabet a 40+ label containing them would be hidden; the head shows it, and nothing tests either (objection 1 is the same gap seen from the other side).
- m13 (LOW): label length 65. A 65-character UNBROKEN label is hidden by the token rule anyway, so only a 65-character label with a dot or colon separates the two; I probed a 65-character dotted label on the head: not shown, as the length rule intends; no test has one.
- m15, m16, m17 (LOW): the label alphabet itself (`/`, `:`, a `+`) is not pinned by any sample.

## Findings
F-PR735-1 MEDIUM-LOW: decide whether `/` and `:` belong in the token rule (objection 1), then pin it. F-PR735-2 MEDIUM-LOW: add a dotted label with a 40+ first segment and a 65-character dotted label (m4, m5, m13). F-PR735-3 LOW: sample labels with `/`, `:` and `+` (m15 to m17).

## Conditions
None block. Coordinator: GX10 16/16 and CI on this exact head; a call on F-PR735-1.
