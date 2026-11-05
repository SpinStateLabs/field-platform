# Review PR 818 (G22 internal secret, rebuild of #374) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `35f060960bf917d28982b59fc23e333dd2370f53`.
Conditions: (1) CI green and full GX10 16/16 on this exact head: it changes a security layer in field-core that every service installs (`install_routes`), and I ran only field-core, not the service suites. (2) Don/architect answers to the PR's 3 decision items before ENFORCE use (not blocking the merge): ENFORCE now 404s both internal routes unless the hash is set; `FIELD_READ_KEY` names come from PR 369 (not on main); no minimum secret length.

## Objections first
1. Fail-closed 404 in ENFORCE with the hash unset changes today's behaviour of two live routes; I found no in-repo caller (the only references are CI edge-block checks that expect 404, which cannot tell "refused by the secret layer" from "refused by the edge": a LOW coverage blind spot, MEDIUM confidence, not run).
2. Read-key equality depends on env names that PR 369 defines; if 369 renames them the refusal silently weakens.
3. No floor on secret length (a 1-char secret passes).
4. Boolean `internal_secret_sha256_present` is on the open /health (by decision; leaks only set/unset).

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. Files under .github/: 0. 8 files (+756/-12). Base is current main 3804d0b9 (merge-base == main).
- Matches the architect decision (comms 20261105-1731): hash-verified `x-field-internal` on exactly verify_hash and rotation_state; 404 for absent/empty/wrong/hash-as-secret; ENFORCE+unset 404, OFF/LOG-ONLY unset warns once; refusal of equality with the perimeter secret and `FIELD_READ_KEY[_<SERVICE>]` in both forms; header pinned by value; 256 length bound; bad value raises at install; counter + presence boolean in /health; `phase_g_check --stage 2` read-only count line. Sender and estate secret file correctly NOT claimed (done-when d).
- Code read: constant-time compares (hmac.compare_digest) for value and hash; empty header refused before hashing (sha256("") cannot open it); hash format re-checked on every request as well as at install; both-set requires both; only refusals on otherwise-enabled routes are counted. No defect found.
- Tests on the exact head (Windows, PYTHONUTF8=1): field-core 1646 passed, 3 skipped (PR says 1648 passed; 2-count difference not explained, probably skip/env, MEDIUM-LOW).
- Not run by me: agent-registry, kill-switch, delegation-authority, spend-governor, federation-broker, sealed-ledger, lifecycle-manager suites; test_phase_g_check.py; the boundary-echo/env-doc lints; the PR's 3 changed existing tests were exercised inside the field-core run (pass).

## Mutants (21; counted from the table; run on g22 + c801 + rotation_r2 + operator_health tests)
| # | mutant | result |
|---|---|---|
| A1 | verify_hash skips internal check | KILLED |
| A2 | rotation_state skips internal check | KILLED |
| B1 | hash compared directly to presented value | KILLED |
| B2 | empty header passes | KILLED |
| B3 | ENFORCE + unset allows | KILLED |
| B4 | LOG-ONLY + unset refuses | KILLED |
| B5 | warns every time | KILLED |
| B6 | never warns | KILLED |
| C1 | no deny counter | KILLED |
| C2 | presence boolean always false | KILLED |
| D1 | header renamed | KILLED |
| E1 | no read-key equality refusal | KILLED |
| E2 | generic read key only | KILLED |
| E3 | no perimeter equality | KILLED |
| E4 | hash-form equality dropped | KILLED |
| F1 | no length bound | KILLED |
| F2 | install does not raise | KILLED |
| F3 | empty-string hash allowed | KILLED |
| G1 | both set: only the hash checked | KILLED |
| P1 | --stage 2 passes on 1 of 2 | KILLED |
| P2 | --stage 2 skips the registry | KILLED |
Totals: 21 mutants, 21 killed, 0 survived (A2+B6+C2+D1+E4+F3+G1+P2 groups: 2+6+2+1+4+3+1+2 = 21).

## Optional LOWs (new PR)
Minimum secret length floor; a CI/edge check that distinguishes the secret-layer 404; the `operator.internal_route_denied_changed` observer event (frozen-set question unanswered in the PR).
