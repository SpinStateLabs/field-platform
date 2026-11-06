# Review PR #629 (docs: itemise Phase G in tasks/todo.md) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on head `d16a57689b066c8ed80a5a31a40092cabd269441`. Two small docs conditions (C1, C2). This head is the follow-up to the earlier reviewer's PASS WITH CONDITIONS on `9a467a87` (comms/inbox/coordinator/20261104-1451-ssl-ff-reviewer-pr629.md); its C1 and F2 are closed (below); its F3 is a follow-up outside this PR.

## Facts (HIGH, read from the head)
- 2 commits (9a467a87, d16a5768); 1 file: tasks/todo.md (+39/-1). Docs only; nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.

## The earlier reviewer's findings, on this head
- C1 (not addition-only; two spec facts and the route list dropped; "Spec (unchanged)" inaccurate): closed. `git diff` against the merge base removes exactly one line, the Phase G item's header, which is replaced by the same header plus an itemisation note; the seven original bullets (Keys, Guarded writes with the route list and "`granted_by` must equal the authenticated operator", Kill-switch, Records with "The DOA roster matches on the id", Session vs Don, Declared rows closed) are all present unchanged as context lines; the "Spec (unchanged)" paragraph is gone.
- F2 (CHANGELOG cite off by one): closed. CHANGELOG.md line 47 on the head carries "PR 53, b273d5b", "PR 51, 34d680c" and "PR 54, c8ecba7", which is what G14 now cites.
- F3 (the runbook v1.2-deploy-rollback.md l.1101 still says PR #36 is not merged while the todo says it is): still open, correctly left out of this PR; the builder opened B-FU-PR629-runbook-pr36.

## Checked and correct (as of the PR head and main at that time)
- The cited commits all resolve on main (I resolved the ones in G1 to G15 and G9, G10, G14, G15 on the earlier review's list and re-checked G11 efe430bc and G8 c2f58643). The cited runbook lines resolve on the PR head's tree: :1101 (the merged list), :1113 (design kept in the Force-Field repository), :1247 (the ten rows), :1391, :1454/:1471/:1484 (the Stage checklists), :1954/:1960/:1971 (TLS phase 1 and RT3-1); ntfy-alerts.md :16; todo.md :372 (D16).
- Public safety: shas, PR numbers and file names only; no estate address, flag value, build id or credential.

## Conditions
**C1 (MEDIUM, confirmed): four "not done" items now contradict main.** The list is stamped "Itemised 2026-11-04", but the entries read as current state ("Evidence of state: ..."). Main has since landed:
- G21 (Stage 3 identity gap), still `[ ]` with "open for the rest": commit 9a2417c0 (lifecycle provision: a refused edit reports `edit_refused` and names `don-admin`; estate manifests list `don-admin`) and f3b6870c on main.
- G22 (internal-only secret), `[ ]` "no merged PR found": commits 9944ee35 (hash-verified internal secret for the two internal routes, `phase_g_check --stage 2`) and d5dd8238.
- G23 (alert senders), `[ ]` "no sender on main": fd0ac135.
- G24 (stage controller), `[ ]` "no code found": ede21674, with b1b229f1 and 75085ae3, and for G26 the repo side b77408cb (Stage 3 plan notice and rollback rehearsal).
A reader of this todo would plan work that is already done. Fix: mark G21 to G24 `[x]` with those commits (and note G26's repo side), or restate each "Evidence of state" as "as of 2026-11-04 (main 97dcfec1)". The Review block in PR #844's todo already lists G23, G24 and G21 as on main, so the two files would also disagree.
**C2 (LOW-MEDIUM, confirmed): the line-number cites into the runbook are already drifting.** On current main `*Stage 3, REQUIRE on all eight` is at l.1500 (the todo says :1484), `## 8. GB10 console hop over TLS` at l.1983 (:1960), `Phase 1 alone does NOT close design RT3-1` at l.1994 (:1971), the ten-row paragraph at l.1246 (:1247). The repo has been moving to symbol or heading cites for this reason (PR 538 and 540: "cite symbols, not line numbers"). Fix: cite the section heading (for example "Stage 3, REQUIRE on all eight") or add "(lines as of main 97dcfec1)".

## Optional (LOW)
- G16, G18, G25 and G27 are labelled "NOT in the repo / coordinator's memory notes", which is honest; they stay unverifiable from the repo.

## Not covered
Resolving PR numbers #33 and #51 against GitHub (the PR says they come from prose); a GX10 light run; CI on this head; the commits cited in G1 to G15 beyond the spot-checks above.
