# Review PR #769 (docs: kill-switch README pre-v1.2 claim, S8-11) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `4f0c60ec8b5042f403b550d5a5112e42c0ba4265` (merge-base 078967e4; draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 1 file: services/kill-switch/README.md (+13/-9). Docs only; nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Merge against current origin/main (869cf2ed): 0 conflicts; main did not touch this README since the merge-base.
- Every STATE.md cite checked on the head: :867 "X1 ARMING COMPLETE on both estates, 2026-09-13" (matches); :899 "N1 `/liveness` lists `canary-gb10` live" (matches); :918-919 Fly 17:25Z "N1 `canary-fly` live after a check-in" (matches); :1004-1009 GB10 `FIELD_KILL_ENDPOINT_ALLOWLIST=canary-agent`, `x3-check` 11/11, kill => endpoint called, same nonce; "Fly: nothing (D7)" (matches). The three replaced claims (pre-v1.2 images, allowlist unset on both, no agent checks in) are indeed contradicted by those entries.
- The rewritten text keeps the Declared marker for anything beyond the dated entries and says the repo cannot observe the estates. Mutants: not applicable to prose; I checked each new sentence against its cite instead (table above: 4 of 4 cites match).

## LOWs (optional, new PR)
1. "Fly: allowlist unset" is inferred from STATE.md's "Fly: nothing (D7)" (X3 + A6 not done on Fly), not stated literally (MEDIUM).
2. Public-repo rule (ROLE-LOOP "no flag value, ... deploy status"): the README now repeats a flag value and estate status. The same text already sits in STATE.md and the old README named the flag and its GB10 setting, so this adds no new class of disclosure, but a stricter reading would want it trimmed (coordinator's call).
3. Stale copies the PR itself lists (agents/README.md:30, the two agents/*/SKILL.md lines) remain; not checked whether S4-20 covers them.
4. Author's claim that test_deploy_docs.py has 5 failures identical on main: not re-run by me (not verified).
