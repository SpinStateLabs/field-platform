# Reviewer (read-only, post-merge): batch cb12 = MERGE 7, main 3425e23f -> 9468b184 (PRs 382 @0dde283, 388 @b59068b, 394 @e57d1ad, 423 @85c13a0, 424 @8c1a223; 21 commits)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `9468b184`.** No earlier file names cb12 or cb11 as a batch; this is that file. Full PR heads: 382 `0dde283598e9359a0b8360896f2b6e649db7c85e`, 388 `b59068b4631e73be3508e357a2fcdfbea269c800`, 394 `e57d1ada70fc6701a978a885de1087651b621fb2`, 423 `85c13a0027767c1998b1b3e53127dbaec9d6c31f`, 424 `8c1a223a92cd35a6d47a20aa4172065420b5e222`.

## Record checked (HIGH, from git and gh)
- 21 commits 3425e23f..9468b184 (STATUS: 21), a fast-forward, 0 nonconforming identities (all Don Hagell noreply on author and committer). 9468b184 is on main.
- A reviewer PASS naming each exact head: 382 in c43 (`20261108-0300-reviewer-c43-deltas-...`, the file name date is not the commit date, `git log` shows 2026-10-30), 388 in c1055, 394 in q25, 423 in q62-q63, 424 in q64. Verifier B 16/16 on 9468b184: `20261101-1331-gx10-verifier-B-batch-cb12.md` (names the sha, says 16/16); verifier A 16/16 on cb11 (`20261101-0529`, the 16-commit subset). PRs 382, 388, 394, 423, 424 CLOSED with a pointer comment each; CI SUCCESS 7/7 on each head.

## Objections first
1. The batch ships the first 422 no-echo handler (`field_core/http_errors.py`, only crosswalk installs it) and an attestation-reporter nesting bound; both are security claims, so I attacked them with mutants rather than read the PASS lines.
2. Later work (PR 431, C-1114 and C-1128 guard) extended the handler to more services after this batch; this review is of cb12 as merged, not of those.
3. The 6 docs and environment-scan test commits (C-831, C-939, C-938, docs soak) have no behaviour to mutate beyond the scan tests; I ran them (62 passed) but wrote no mutants for them.

## Measured (GX10 ~/ff-work/wt-cb12 at 9468b184, python -B, own venv + uvicorn installed for the latency test)
field-core `test_http_errors_c1018` 19 passed; crosswalk `test_pack_422_no_echo_c1018` 9 passed; attestation `test_parse_verify_window_c1072` 44 passed; `test_environment_doc` 62 passed; sealed-ledger `test_ledger_latency_100k` 3 passed, 1 skipped (it failed 1 first for a missing `uvicorn` in my venv, environment only). The 16-suite is the verifier's report, not mine.

## Mutants (38 rows; source restored after each, worktree clean)
| Claim | Killed | Survived |
|---|---|---|
| H1 an unexpected field NAME is replaced in `loc` (http_errors.py) | 1 | 4 (3 equivalent: the known-names filter already redacts it; 1 gap: the `REDACTED_NAME` value is unpinned) |
| H2 value and assertion messages are a fixed phrase | 3 | 2 (1 equivalent: the unlisted-kind fallthrough also redacts; 1 gap: the exact phrase is unpinned) |
| H3 kinds not on the allow-list get a fixed phrase | 4 | 1 (gap: the exact phrase) |
| H4 `loc` keeps only names the app defines (a dict key is redacted) | 3 | 3 (2 inert additions; 1 gap: a list index in `loc`) |
| H5 declared field, parameter and alias names stay | 2 | 3 (gaps: `param.name`, aliases, the `body` root) |
| A1 nesting bound checked before `json.loads` (signing.py) | 6 | 0 |
| A2 `RecursionError` becomes a named refusal | 2 | 0 |
| A3 a non-str verify key is a named refusal | 1 | 3 (gaps: each of the AttributeError, TypeError and ValueError arms of the except tuple is separately unpinned) |
Totals counted from the table: killed 1+3+4+3+2+6+2+1 = 22; survived 4+2+1+3+3+0+0+3 = 16; 38 rows. Of the 16 survivors, 6 are equivalent or inert and 10 are unpinned detail (messages, shape, arms).

The central property, that a 422 never repeats the caller's text, IS pinned: mutants that echo the message (H2, H3) or keep a caller-chosen key (H4) were killed. What is not pinned is the SHAPE the caller sees (phrases, `body` in `loc`, list indexes, aliases).

## Conditions
- C1: none blocking (merged; record complete; the no-echo claim survives its mutants).
- C2: H1, H2, H3, H4, H5 and A3 are below 4 kills; the 10 gaps go to one follow-up test PR (they are cheap: assert the phrases, `loc[0] == "body"`, an aliased field, a list index, and one test per except arm).

## Findings (non-blocking; new PR only)
- F-cb12-1 LOW: assert the exact `Invalid value` and `Value error` phrases and the `(field)` marker.
- F-cb12-2 LOW: `loc` shape (the `body` root, a list index, an aliased field, a path or query parameter name).
- F-cb12-3 LOW: one test per arm of `except (AttributeError, TypeError, ValueError, UnsupportedAlgorithm)` in signing.py.
