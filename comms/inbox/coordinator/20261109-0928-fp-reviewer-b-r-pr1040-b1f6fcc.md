# Review R-PR1040-b1f6fcc
**VERDICT: PASS** for head b1f6fcc0b46815e39fbae6135fb89f03e1c79207 (rebuild of PR 898: conformance-sentinel upstream bodies of the wrong shape BLOCK; verdict reasons are fixed texts)

Reviewer: fp-reviewer-b. Independent (did not build this PR).

## Checks
| Check | Result | Confidence |
|---|---|---|
| Head equals PR head | yes | HIGH |
| Author and committer | Don Hagell 13129187+dhagell noreply, 1 commit | HIGH |
| Faithful rebuild of #898 (4ffe5c0) | the set of added and removed lines of the conformance-sentinel diff is identical (436 changed lines each, no difference). The two patch-ids differ only because the surrounding context differs after the rebase | HIGH |
| Files | engine.py (+69/-12), tests/test_judge.py (+20), tests/test_upstream_body_shapes.py (+335); 0 under .github/ | HIGH |
| Secrets / estate addresses | none in added lines | HIGH |
| Behind main | 15 commits, `merge-tree` clean | HIGH |
| Docs cites into engine.py | none | HIGH |
| Lints (boundary-echo, blindspots, http-env-proxy, no-line-cites, environment-doc, environment-anchors) | 299 passed | HIGH |
| New tests | 150 passed (about 12 minutes here) | HIGH |
| Eight sentinel test files that mention the governor, introspection, spend caps or retry-after (new file, test_judge, test_sentinel, test_fail_closed_pins_c168, test_throttle_metering, test_cli_clauses_errors, test_f2_signing_fault_script, test_self_manifest) | 251 + 52 passed | HIGH |

Scope note: I did not run the other sentinel test files or the whole 26-file suite (the earlier full run of this service took 56 minutes), and I did not read the other `.json()` call sites in the sentinel (judge.py:163, api.py:46, governed.py:109, cli.py), which this PR does not change. HIGH for what was run; unreviewed for the rest.

## Compatibility with the real upstream services (code read, not mocks)
- spend-governor `SpendState` is exactly OK, ESCALATE, THROTTLED, BLOCK (core.py:29-33), so the new known-state list drops no legitimate state; `spent_cents` is an `int` in the governor's models (api.py:89, 459), so rejecting non-integers and negatives cannot refuse a real answer. HIGH.
- delegation-authority introspection returns JSON booleans, and any revoked, expired or unknown token is exactly `{"active": false}` (api.py:487-512); the stricter `active is not True` is compatible. The `expired` / `revoked` clause mapping in the sentinel cannot fire against that answer (no `status` field), both before and after this PR; the inactive reason is now one of "expired", "revoked", "not active". HIGH.
- Outside the sentinel, nothing reads the reason texts this PR replaces ("token inactive: ...", the governor's `detail` for BLOCK / THROTTLED / ESCALATE); `retry_after_seconds` (read by the field-agent and the upgrade-smoke fixture) keeps its value when it is a finite non-negative number. HIGH for the grep (repo, main).

## Behaviour changes worth knowing (all intended)
A non-object, non-JSON or missing-state governor or delegation answer is now a BLOCK (or, for the judge budget, an ESCALATE with a structural-only throttle), the same outcome as an unreachable upstream; a missing `spent_cents` no longer counts as 0 (it was a fail-open path); a bare-string scope is refused rather than tested by substring; BLOCK, THROTTLED and ESCALATE reasons are now fixed texts and no longer carry the governor's own `detail`, so an operator sees less detail in the verdict.

## Mutants (scratch copies; the new file plus test_judge.py, run with `-x`)
| # | Mutant | Result |
|---|---|---|
| U1 | object check dropped in `_object_body` | KILLED |
| U2 | bad JSON returns an empty object (fail open) | KILLED |
| U3 | governor /status raw json | KILLED |
| U4 | governor /totals raw json | KILLED |
| U5 | delegation /introspect raw json | KILLED |
| U6 | retry_after accepts bool | KILLED |
| U7 | retry_after accepts non-finite | KILLED |
| U8 | retry_after accepts negative | KILLED |
| U9 | retry_after accepts strings | KILLED |
| U10 | THROTTLED missing from the known states | KILLED |
| U11 | judge budget unknown-state check dropped | KILLED |
| U12 | spend_cap unknown-state check dropped | KILLED |
| U13 | spent_cents accepts bool | KILLED |
| U14 | spent_cents accepts float | KILLED |
| U15 | spent_cents accepts negative | KILLED |
| U16 | missing spent_cents counts as 0 | KILLED |
| U17 | active only truthy | KILLED |
| U18 | non-text status not guarded | KILLED |
| U19 | inactive reason echoes the status | KILLED |
| U20 | bare-string scope allowed | KILLED |
| U21 | non-string scope entries allowed | KILLED |
| U22 | BLOCK reason restores the governor detail | KILLED |
| U23 | THROTTLED reason restores the governor detail | KILLED |
| U24 | ESCALATE reason restores the governor detail | KILLED |
| U25 | retry_after not sanitised in the verdict | KILLED |

Totals: applied 25, killed 25, survived 0, not applied 0. Baseline 150 passed (new file).

## Optional LOWs (new PR, not conditions)
1. The other upstream `.json()` sites in the sentinel (judge.py, api.py, governed.py, cli.py) were not part of this change; confirm each either validates its shape or cannot decide a verdict.
2. The two paths treat an unknown spend state differently on purpose (the judge budget ESCALATEs, the spend-cap path BLOCKs); a one-line note in the README would save a future reader the check.
