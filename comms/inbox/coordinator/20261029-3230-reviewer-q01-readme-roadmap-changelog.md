# Q-01 reviewer report: README.md, ROADMAP.md, CHANGELOG.md numbers, counts and dates (main b1872ee; 73, 43 and 90 lines)

VERDICT: the three files are short and mostly honest, but five statements are stale against main: the system count, the test count, three ROADMAP delivery statuses, and the CHANGELOG, whose "Unreleased" section ends before PR 56.

OBJECTIONS FIRST
1. The files are small, so "every number and date" is a short list; the findings below are all of them that I could check against the repository, not a sample.
2. Test counts come from my own GX10 runs (Python 3.12.3), which are not the CI matrix totals.
3. "12 systems" is a product statement; the code has 14 service directories because two are not governance systems; whether the README should count them is an editorial choice.

ASSUMPTIONS
1. Main b1872ee (PR 95). `ls services/` = 14 directories: agent-registry, attestation-reporter, claude-approver, compliance-crosswalk, conformance-sentinel, delegation-authority, federation-broker, force-gateway, incident-replay, kill-switch, lifecycle-manager, ops-console, sealed-ledger, spend-governor. [HIGH]
2. Test totals from my verify runs on the PR 95 head (C-190): core_services 2,181 passed (field-core, sealed-ledger, delegation-authority, spend-governor, kill-switch, federation-broker), tools 1,925, agent-registry 238, conformance-sentinel 109, incident-replay 74, compliance-crosswalk 160, force-gateway 208, lifecycle-manager 185, attestation-reporter 66, ops-console 171, claude-approver 101, field-agent 118: sum 5,536 passed (plus 8 skipped). [HIGH: arithmetic 2181+1925+238+109+74+160+208+185+66+171+101+118 = 5,536]

REASONING
1. F-Q01-1 (LOW) README.md:3 "12 enterprise AI-governance systems", :26 "one directory per governance system (12 total)", :33 "The 12 systems": the table lists 12 and they all exist; `services/` holds 14: ops-console (ROADMAP names it "plus ops-console") and claude-approver (pilot S2, not in the README or ROADMAP). STATE.md says "thirteen services" (before claude-approver). Three documents, three counts (12, 13, 14). [HIGH]
2. F-Q01-2 (LOW) ROADMAP.md:37 "209 tests, CI green (py 3.11-3.14 + x86_64 compose)": 5,536 passed on the GX10 today; 209 is stale by a factor of about 26. The CI matrix claim (3.11-3.14) matches ci.yml:20-21. [HIGH]
3. F-Q01-3 (LOW) ROADMAP.md:10-14 delivery statuses: Conformance Sentinel "in progress (log-only ✓ · scorecard · semantic judge · self-manifest)": `mode.py`, `seeded.py`, `measure.py`, `judge.py`, `self_manifest.py` exist and are tested; FORCE Gateway ADR delta "queued (sampled hygiene judge · trend alerts · fail-open+capped)": `hygiene_judge.py`, `drift.py`, `telemetry.py` exist (and enforce mode, F1, which contradicts "fail-open", see Q-02 F-Q02-1); Compliance Crosswalk "queued (gated suggestions · evidence-pack generator · reg-version staleness)": `suggestions.py`, `evidence_pack.py`, `staleness.py`, `regwatch.py` exist. The file's own rule ("records what is built, not a wishlist") is not met by "queued". [HIGH]
4. F-Q01-4 (LOW) CHANGELOG.md: the only section is "Unreleased" (90 lines); its newest entries are Phase G Stage 0 follow-ups, claude-approver v0 and the field-client lift (about PR 55). Grep for the later work: ntfy 0 hits, alerts 0, break-glass 0, "duplicate JSON" 0, rotation 0, frame-ancestors 0, D-22 0. PRs 56-95 (alerts opener, break-glass sealed row, alias squat, observer witness, FieldClient proxy, gateway key hygiene, console frame headers, registry retired guard, operators-file loader) are absent. There is no dated release heading anywhere. [HIGH]
5. README.md:46-47 names a personal venv path (`C:\Users\donal\.venvs\field-platform`) and "developed on 3.14": information, not an error; the CI matrix does include 3.14. INFO, F-Q01-5. [HIGH]
6. Checked and fine: the 12-row table's service names all exist as directories; the nine ROADMAP items map to existing `services/*` directories (each marked ✓); the `docs/INTEGRATION.md` and `packages/field-agent` references exist; "Python >=3.11" matches the CI matrix floor. [HIGH]

CONCLUSION
Update the counts (14 services, about 5,500 tests, or drop the number), mark the three ROADMAP deltas as built, and backfill the CHANGELOG from PR 56 on (the coordinator's PR list is the source). Not done: dates inside CHANGELOG bullets against the git log.
