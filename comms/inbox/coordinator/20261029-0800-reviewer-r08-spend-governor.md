# R-08 reviewer report: services/spend-governor read and mutants (main 9292246)

VERDICT: arithmetic of the caps and the D1 throttle is well pinned; the cap WINDOW (daily / monthly / total) is not pinned at all. 104 mutants, 84 killed, 20 survived; 6 of the survivors are in `window_start`.

OBJECTIONS FIRST
1. My generator only flips `if` conditions with a raise/return/continue body and single comparisons: no arithmetic, argument or boolean-operator mutants, so 84/104 is not a coverage figure.
2. The suite (101 tests) takes 7 s, so a survivor means no test looks, not that a test is slow.
3. I read core.py's `evaluate`, `window_retry_after`, `action_totals`, `window_action_rows`, `window_start`, `SpendCapConfig`; I did not read all of api.py (569 lines) or provisioning.py/cli.py.

ASSUMPTIONS
1. Main 9292246; three isolated clones `~/ff-work/r08{a,b,c}`; each run used the spend-governor suite only (`TESTS_ONLY=tests`, cwd services/spend-governor). [HIGH]

REASONING
1. core.py: 56 mutants, 46 killed, 10 survived. api.py: 47 mutants, 38 killed, 9 survived. usage.py: 1 mutant, 0 killed, 1 survived. [HIGH]
2. MEDIUM, F-R08-1: `window_start` (core.py:319-324). All six mutants on L320 and L322 (`daily` / `monthly` condition to False, True, `!=`) survive: no test distinguishes the daily, monthly and total windows of a CAP. With `if period == "daily"` forced True a `total` or `monthly` cap would reset its spend at midnight, a fail-open on a money limit, and no test would go red. The only periods tests name are `daily` (test_spend_governor.py:22, test_throttle.py:102) and a parametrisation at test_throttle.py:601. [HIGH]
3. LOW, F-R08-2: `SpendCapConfig._at_least_one_limit` (core.py:99), `if all limits None: raise`: mutant to False survives. A cap with no limit would be accepted and `evaluate` returns OK forever. Not reachable through `from_manifest` (it always sets limit_cents) but reachable through `PUT /caps` with an empty cap body. [HIGH on the survivor, MEDIUM on reachability: not probed]
4. LOW, F-R08-3: `evaluate` (core.py:794) `if open_escalations:` survives: an unresolved escalation does not have to keep the state ESCALATE, per the docstring's precedence list. Also L538 `if esc.resolved: raise` in `add_escalation_if_none_open` survives. [HIGH]
5. LOW, F-R08-4: `PUT /caps/{id}` (api.py:270) and `PUT /policies/{id}` (api.py:456): the path/body `agent_id` mismatch 422 is untested (mutant to False survives both). A body naming another agent would then be stored under the body's agent while the operator guard saw the path. [HIGH]
6. LOW, F-R08-5: `GET /policies/{id}` (api.py:464): both `if policy is None` mutants survive, i.e. no test reads an existing policy (always-404 survives) nor the 404; `GET` spend status 404 for no cap (api.py:209) untested. [HIGH]
7. LOW, F-R08-6: usage.py:120 `window_tokens_after >= policy.token_rate_limit` -> `>`: a burst exactly at the limit is untested; api.py:236 throttle detail label (`kind == "action"`), api.py:332 default sentinel note: text only. [HIGH]
8. EQUIVALENT: api.py:155 (`_ledger_note`, ledger None: the `None.append` raises into the swallowing `except`), api.py:173 (`action is not None`: a None action matches no limit), core.py:114 (`>` vs `>=` at 1e-9 on a float diff). [MEDIUM: reasoned, not probed]
9. Pinned: `evaluate` limits and 80% threshold arithmetic, `action_totals` (Option A max rule), `window_action_rows`, `window_retry_after` (all mutants killed in lines 695-770), metering failure behaviour (the ledger-down path is deliberately swallowed at api.py:155-160 so spend records are kept; test coverage on it: killed). [HIGH on mutants, MEDIUM on "behaviour is right": design choice per the code comment]

CONCLUSION
One MEDIUM (window_start untested: add a test per period asserting the start timestamp and that a total cap does not reset at midnight), five LOW gaps. No defect found in the arithmetic. Not done: arithmetic/argument mutants, cli.py, provisioning.py, a full read of api.py.
