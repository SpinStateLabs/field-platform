# C-62: the three C-61 loose ends (teammate-don-reviewer, 2026-10-28) - READ-ONLY, git/gh only

Method (HIGH for what it measures): for each branch, every ADDED line of its patch against its merge-base with main (non-trivial = 3+ characters, trimmed), looked up in main's version of the same file (`git show origin/main:<file>`); lines not found are listed. A line missing from main means "reworded, moved, or dropped", not "lost": each class below was then checked by name on main.

## 1. claude/adr-0072-estate-kill-watcher (#11, closed) -> DELETE (HIGH)
`git rev-parse` of the two branch trees: this branch and its successor claude/adr-0072-estate-kill-watcher-r2 (#12, MERGED 2026-10-21) are both tree 0e2f3e9c62d3. Identical content; the only added line absent from main (`deadline = time.time() + 60` in tools/tests/test_estate_kill_watcher.py) is a test line main later changed.

## 2. claude/adr-0074-crosswalk-gate-controls (#10, closed) -> DELETE (HIGH, dropped on purpose)
14 of 207 added lines are absent from main, in 7 files: the FC-E-04 mapping citing EU AI Act Art. 14 para 1 as a PARTIAL mapping (mapping.py, test_crosswalk.py) and the restated figures `17/52` (README, SPEC, api description, test_pack_api.py, STATE.md). PR #13 (the merged successor) body states: FC-E-04's EU AI Act Art. 14 para 1 "partial" citation is now `pending` because its fit to a deployer command blocklist was not verified against the text. Main's STATE.md says `cited entries 16/40 -> 16/52 (same cited count; 12 new pending entries)`, not 17/52. This matches tasks/lessons.md ("never claim compliance"; cite only verified text). So the closed branch carried the unverified citation that the successor deliberately removed.

## 3. feat/pg-s0-guards (#40, closed, "superseded by #41") -> DELETE, confidence MEDIUM
77 of 4,428 added non-trivial lines are absent from main, in 17 files (largest: kill-switch api.py 15, operator_auth.py 13, operator_health.py 12, operator_observer.py 11, operator_keygen.py 5, agent-registry api.py 4, ops-console api.py 3, lifecycle api.py 2, README/runbook/phase_g_check/test_phase_g_check 1-2 each). I checked the content classes by name on main, all present in later form:
- phase_g_check's `fok_` guard on key-shaped operator ids: main tools/phase_g_check.py:612 has it (strengthened to `fullmatch`); the "Pairing" item exists on main as item 6 (line 60, `status_pairing` line 617); the test faults `ks_drops_on_behalf_of` and `ks_on_behalf_of_forged` exist on main (test_phase_g_check.py:833-851).
- `sweep_kill` explicit-only scope: main operator_auth.py:181 `EXPLICIT_ONLY`, used at :400.
- registry `operator_on_behalf_of`: main agent-registry api.py:38 and :276-278 (records it only through `bind_on_behalf_of`, a reserved ledger key; the #40 text `recorded["operator_on_behalf_of"] = who` was replaced by design).
- ops-console `self.client.post("/events", ...)` raw append: replaced on main by the signed append of #52 (`signed_append_body`).
- observer header-less fetch wording and README rows: reworded by #45 (observer whole-exchange deadline).
- the older scope names in the #40 operator_auth hunk (`assert_operator` in a scope set): main rejects that scope (REJECTED_SCOPES), so removed deliberately.
NOT verified: all 77 lines one by one (the sampled and class-matched ones account for most; I did not diff each against #41/#42/#45). If Don wants zero doubt before deleting, push a tag first (`git push origin <sha>:refs/tags/archive/pg-s0-guards-40`, sha below); GitHub also keeps refs/pull/40/head after the branch is deleted. Tip: a15e893 (recorded in the C-63 script).

## Verdict table
| Branch | Verdict | Evidence line |
|---|---|---|
| claude/adr-0072-estate-kill-watcher | delete | same tree as merged #12 |
| claude/adr-0074-crosswalk-gate-controls | delete | #13 body: the Art. 14 partial citation became `pending`; main says 16/52 |
| feat/pg-s0-guards | delete (MEDIUM; tag first if in doubt) | later forms of the sampled hunks on main; PR #41 title "supersedes #40" |
