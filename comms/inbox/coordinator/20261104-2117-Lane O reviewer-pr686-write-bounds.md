# LANE O review: PR 686 (sealed-ledger S5-10: bound write-route text, hide OSError text) @ bc23907b

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head bc23907b, 1 commit, 0 behind origin/main, merge clean, Don Hagell numeric noreply. api.py +23/-12, tests +137, docs/ENVIRONMENT.md 1 row (anchor 464 -> 475), boundary_echo_allowlist.txt -1 line (the `create_app.hold_status::api-reply` entry removed).

Objections first: (1) the cap covers only some free text: the append PAYLOAD is deliberately uncapped (the new test pins that it stays unbounded), and `append_event`, `export`, `place_hold`, `release_hold` and `list_events` still echo failure text per the remaining allowlist entries; this PR claims only the routes it names. (2) The `retention_apply` change narrows nothing: an `except OSError` after earlier handlers; a widened `except Exception` is not distinguished by any test (equivalent for the OSError claim, but it would turn an unexpected error into a 500 with a type name). (3) The blank-event_type validator returns the value as sent; the PR does not claim that, and no test pins it (my inference, see B3).

Baseline (unmutated, measured): the eight older sealed-ledger files that exercise these routes (test_sealed_ledger, test_ledger_retention, test_422_no_echo_sealed_ledger_c1114, test_guarded_routes_ledger_c511, test_ledger_c2_hardening, test_ledger_rotation, test_export_bundle, test_caller_signing_f2b) 348 passed, 4 skipped; tools/tests/test_boundary_echo_lint_c505.py 61 passed; `python tools/environment_anchors.py --check` at this head: 0 wrong anchor row(s) (`api.py:475` is the real `os.environ.get("FIELD_EXPORT_ROOT"...)` line). The full 828-test sealed-ledger suite was not rerun per mutant (138 s each); survivors were checked against those eight files plus the lint.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 limits are 200 (names) and 2000 (reasons) | 4 | 4 | 0 | 0 |
| B2 every name and reason field on every write route is capped | 8 | 8 | 0 | 0 |
| B3 blank event_type refused; stored value unchanged (second half is my inference) | 5 | 4 | 0 | 1 |
| B4 GET /hold OSError: 503, "ledger busy" prefix, type name only | 5 | 5 | 0 | 0 |
| B5 retention apply OSError: 500, type name only, LedgerCorrupt unchanged | 6 | 4 | 1 | 1 |
| Total | 28 | 25 | 1 | 2 |

Totals counted from the table: 28 = 25+1+2; no invalid, no noapply. Fields covered by B2: AppendRequest event_type and agent_id; RotateRequest operator and reason; HoldRequest by and reason; HoldReleaseRequest by; RetentionApplyRequest operator.

Survivors, 2:
- Real gap (inferred behaviour): B3 `return v.strip()` in the event_type validator; the stored text is not shown to be unchanged. The PR does not claim this.
- Equivalent for the claim: B5 `except Exception` in place of `except OSError` on retention apply; only an OSError path is tested.

Conditions: optional only: assert the stored event_type keeps its padding, or state that it is stripped. Confidence: HIGH on counts, MEDIUM on classification. Token/cost: I do not know.
