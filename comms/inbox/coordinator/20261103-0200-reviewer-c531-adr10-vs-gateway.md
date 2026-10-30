# C-531 (Lane 9, cloud-reviewer, read-only, no GX10): ADR Pack 10 (FORCE Gateway) against services/force-gateway/src, main b929f12

VERDICT: of 22 statements checked, 12 TRUE, 6 PARTLY TRUE, 2 STALE (a path and a flag spelling), 2 UNVERIFIABLE from the repository. The observer design (no model for injection, structural telemetry, sampled judge, trend alerts, fail-open bypass, metadata-only store) is built as the ADR says; the "notifies the owner" guardrail is a ledger record, not a notification, and the spend-cap behaviour differs from the guardrail table. The ADR already carries the 2026-10-29 "Superseded in part" note for enforce mode; I checked it too. No secret read or printed.

OBJECTIONS FIRST: (1) the ADR is a design record; statements of intent are not defects, so I list only what a reader would take as built. (2) I read source; no test or service run (no GX10). (3) "Notifies the owner" could be satisfied by a ledger event the owner reads; I flag the gap because a ledger row nobody is told about is not a notification. (4) The superseded note is dated 2026-10-29 and main has moved (C-180, D-24 flag parsing); a note can go stale too.

ASSUMPTIONS: main b929f12; src = services/force-gateway/src/force_gateway (1,887 lines; api.py 1,103).

TRUE
1. ADR 1: injection involves no model: presets.py:1-14 (preset blocks assembled from vendored `data/protocol.md`; "No FORCE language is authored here"), PRESETS analysis FORCE, brainstorm FCE, draft FC, audit FRCE (presets.py:19-24). HIGH.
2. ADR 1: parser-based structural telemetry: store.py:36 `AGG_FIELDS` (confidence_tags, clean_of_flattery, cot_structure, ...), telemetry.py (74 lines). HIGH (read of the field list; the parsers were not each read).
3. ADR 1/2: semantic hygiene by a sampled judge on a cheap model class: hygiene_judge.py:1-6, :24-27 (`claude-haiku-4-5-20251001`, rubric `hygiene-v1`), api.py:657-690 (deterministic 1-in-N stride, `sample_every`). HIGH.
4. ADR 1: judge prompt-defined, switchable; thin adapter: hygiene_judge.py `resolve_hygiene_judge` (mock or real); one real provider. HIGH for the seam, see row 14 for "provider".
5. ADR 2: alert on two consecutive windows outside the baseline band, never a single point: drift.py:7-12, :91-107 (`consecutive_out >= 2`), recovery re-arms (:92-94). HIGH.
6. ADR 2/3: a judge-model or rubric change resets baselines: drift.py:14-17, :62-75 (series keyed on model and rubric version). HIGH.
7. ADR 3: no retrieval pipeline; a fixed versioned rubric; append-only local store: hygiene_judge.py:29 `RUBRIC`, `RUBRIC_VERSION`; store.py:11 (`drift_scores` append-only, replayed at startup, rebuilds baselines deterministically). HIGH. (The telemetry rows are pruned, row 15.)
8. ADR 4: telemetry stores metadata and scores, not full content: store.py:6-7 ("metadata and counters only; never response text"). HIGH (docstring read; I did not grep each insert).
9. ADR 4: the proxy fails open: store fault is treated as an instrumentation fault (store.py:20-21), `_enter_bypass` (api.py:644-652), latency budget over 250 ms default drops to bypass (api.py:799-801, :1029-1030). HIGH.
10. ADR 4: bypass windows are visible in the coverage metric, never silent: api.py:413 ("bypass windows are visible here"), :719-723 (`bypassed`, `bypass_entries`, `bypass_reasons`), `bypass_remaining` not persisted. HIGH.
11. ADR 4: judge spend capped as a manifest value the Gateway must respect: api.py:669-683 (no governor, governor unreachable, no cap, governor error, budget: each skips the judge and counts it), self_manifest.py. HIGH for the skip; see row 17 for what "bypass" means.
12. ADR 4 (superseded note): with enforce, `/v1/messages` answers 401 without `x-field-agent-id` and `x-field-token`, 403 on BLOCK or ESCALATE, 503 with no upstream call when the sentinel is unreachable, before passthrough and bypass: api.py:25-47 (docstring), :553-586. HIGH.
PARTLY TRUE
13. ADR 4 / table: "bypass ... and notifies the owner": `_enter_bypass` (api.py:644-652) says "the owner is notified" but its only action is a ledger event `gateway.bypass`, written best-effort (`_ledger_event`, :529-538, whose own docstring calls the ledger append "Owner notification"). There is no push, mail or alert call in force-gateway src (grep: notif/ntfy only in those two comments). A reader of the ledger can find the bypass; nobody is told. HIGH (read, grep).
14. ADR 1: "a thin provider adapter ... vendor-agnostic": the judge and the upstream client exist as seams (mock plus the Anthropic API); there is one real provider. MEDIUM.
15. ADR 3: "telemetry lands in an append-only local store": `drift_scores` is append-only, `telemetry_records` is pruned to the newest `max(retain, N)` rows (store.py:6-10, `DEFAULT_RETAIN = 10_000`, `FORCE_TELEMETRY_RETAIN`); counters are updated in place. HIGH.
16. ADR 2: "the Gateway ... never blocks a call (see ADR 4)": true in observer mode, the default (`FORCE_GATEWAY_ENFORCE` off); the ADR's own superseded note says so, and with enforce on the gateway blocks with 401/403/503. MEDIUM-HIGH (already noted in the ADR).
17. ADR 4 / table: "on ... judge spend at cap, the Gateway drops to bypass mode - traffic flows uninstrumented": at cap only the JUDGE is skipped (`judge_bypassed`, api.py:677-683); structural instrumentation of the traffic continues. Bypass mode proper is entered by a fault or the latency budget (`_enter_bypass` reasons). HIGH.
18. ADR 2: "calibration is a periodic human scoring of the same samples; quarterly human calibration": no calibration tooling or record in src or tests. A process statement, not code. MEDIUM.
STALE
19. ADR 3: "the canonical FORCE prompt (`docs/FORCE_PROMPT.txt`)": that file does not exist anywhere on main (find, grep). The prompt the gateway injects is vendored `data/protocol.md` (presets.py:3-6), copied from `plugins/force/skills/force/protocol.md`. HIGH.
20. Superseded note: "`FORCE_GATEWAY_ENFORCE=1` (exactly `1`; default `0` ...)": since C-180 / D-24 the flag accepts `1 true yes on` and `0 false no off` (case-insensitive) and an unrecognised value refuses to start (api.py:290-301). Only `FORCE_GATEWAY_MOCK` stays exact "1". HIGH. Side note: that refusal message still prints the first 40 characters of the value (api.py:297-299): open card C-502 (HIGH).
UNVERIFIABLE FROM THE REPOSITORY
21. Economics note ("injection adds approximately zero marginal cost", "judge cost = sample rate x traffic x judge tokens"): no measurement in the repository.
22. "built second, after the Sentinel PoC gate; dogfoods immediately on Spin State's own traffic": a roadmap and estate statement. Not checkable from source (and not a deploy-status claim I can confirm).

FINDINGS (for cards)
- F-C531-1 MEDIUM (doc and code comment): row 13: the ADR table and the `_enter_bypass` docstring say the owner is notified; the code writes a ledger event only. Either wire a notification (the alerts package exists: packages/field-core alerts) or say "recorded in the ledger".
- F-C531-2 MEDIUM-LOW (doc): row 17: at spend cap the judge is skipped, instrumentation continues; correct the guardrail table or the code.
- F-C531-3 LOW (doc): row 19: `docs/FORCE_PROMPT.txt` does not exist; name `data/protocol.md`.
- F-C531-4 LOW (doc): row 20: the superseded note's "exactly 1" is out of date (C-180); and row 15's "append-only" needs "drift_scores only; telemetry rows are pruned".
- F-C531-5 LOW: row 18: no calibration record exists; say planned.
The same pattern as C-529 and C-530: each ADR pack states one or two guardrail behaviours (owner notification, retrieval, isolation) more strongly than the code does.

CONCLUSION: the Gateway code matches the ADR on injection, structural telemetry, the sampled judge, drift alerts, fail-open bypass, the coverage metric and the metadata-only store (HIGH, read). It does not notify an owner (HIGH), skips only the judge at the spend cap (HIGH), cites a prompt file that is not in the repository (HIGH) and its superseded note's flag spelling is out of date (HIGH). I do not know the economics or the dogfood claim.
