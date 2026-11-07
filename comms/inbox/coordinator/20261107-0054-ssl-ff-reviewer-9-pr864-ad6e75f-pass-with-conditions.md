VERDICT: PASS WITH CONDITIONS on ad6e75f739a545792aa9624794ed725fb423538c  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). This PR addresses F3, F4 and F5 of my own red-team card R-RT-HARD-4; I did not write it. F4 and F5 are closed; F3 is closed only for an opt-in mode, the default is unchanged. The condition is a decision and a follow-up, not a defect of the change.

R-PR864-ad6e75f, PR 864 (operator-layer hygiene: verifier token off argv, no plaintext override, 16-hex fingerprints). Applies to this head only. The fetched pull/864/head is ad6e75f7; one commit on main 41afda50 (92 behind); `git merge-tree` clean. Nine files: renew_token.py +10/-3, estate_probe.py +1/-3, operator_keygen.py +6/-6, two runbooks, four test files. Nothing under .github/.

OBJECTIONS FIRST
1. F3 is closed only if an operator opts in. The default `{new_token}` mode is unchanged (the builder says so: existing cron lines and the runbook keep working), so the new token id is still on the verifier's argv, visible in the host's process listing, for every renewal that does not pass `--verify-token-env`. The PR calls moving cron to the new flag "a follow-up for Don". Until then the exposure I reported is unchanged on every deployed schedule. MEDIUM-LOW (the token id is a reference, not the operator key; I rated F3 LOW). HIGH.
2. F4 is closed for estate_probe.py and NOT for tools/phase_g_check.py, which still has `--allow-plaintext` (phase_g_check.py lines 761 and 817: http to a non-private host with the secret is allowed under the flag). I grepped the head: those are the only two remaining occurrences in code. The PR flags it and leaves it for a follow-up. The inconsistency I named (estate_probe permitting what renew_token refuses) now sits in the gate tool instead. LOW-MEDIUM. HIGH.
3. In `--verify-token-env` mode the child gets `dict(os.environ, RENEW_NEW_TOKEN_ID=new)` (renew_token.py line 1330): the verifier inherits the renewer's WHOLE environment, which includes FIELD_SHARED_SECRET and FIELD_OPERATOR_KEY when the operator supplied them that way instead of by file. Not new (the dictionary was already built this way) but the new mode now pushes the one new datum into that environment, so the verifier's environment is the thing to keep clean. The new test records only the token variable. LOW. HIGH on the read, not run with a real secret in the environment.
4. F5 prints 16 hex in the four `--check` sites; the generation line (`fingerprint:` via field_core.operator_auth.key_fingerprint) still prints 8 hex, which the PR states and leaves (a separate change). So within one tool, a freshly generated key shows an 8-hex fingerprint and `--check` shows 16 of the same key. LOW. HIGH on the read.
5. The estate_probe test asserts the flag's absence by reading the source file for the string "allow_plaintext" (a text match, brittle but it pins the removal) and by the argparse error. LOW.

ASSUMPTIONS
A1 The runbook edits (two lines) only describe the removal; I read them in the diff. A2 "The 8-hex fingerprint was grindable" (rotation_events' own note, the reason for F5) is the policy; I did not re-argue it.

REASONING / CHECKS
1. Diff read in full: `--verify-token-env` added; when set, `{new_token}` in --verify-cmd is refused (exit 2, nothing sent), and the "must pass {new_token}" rule is skipped for it; estate_probe's flag and its use are deleted so cleartext to a non-private host with a secret is refused unconditionally; operator_keygen prints `[:16]` at four sites. HIGH.
2. Identity: 1 of 1 commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, from tools/): `-k rt4` in test_renew_token.py 2 passed (185 tests there, 183 deselected; the full file is about 185 subprocess tests and was not run); estate_probe `-k "rt4 or cleartext or plaintext or check"` 4 passed; test_operator_keygen_format2 + test_operator_keygen_stage0 + test_environment_doc 111 passed, 1 skipped; `environment_anchors.py --check` 0 wrong anchor rows (the tools' line numbers moved by these edits and the doc still holds). HIGH.
4. Mutants on a copy of the head against the tests named above (-x, a kill = pytest rc 1):

| id | mutation | result |
|----|----------|--------|
| R1 | {new_token} allowed in env mode | KILLED |
| R2 | env mode still requires the placeholder | KILLED |
| R3 | RENEW_NEW_TOKEN_ID not set | KILLED |
| R4 | the flag is parsed but ignored (always the argv mode) | KILLED |
| E1 | `--allow-plaintext` restored | KILLED |
| E2 | the cleartext refusal removed | KILLED |
| K1 | `--check` row fingerprint 8 hex | KILLED |
| K2 | format 2, current key without expiry: 8 hex | KILLED |
| K3 | format 2, current key with expiry: 8 hex | KILLED |
| K4 | format 2, next key: 8 hex | KILLED |
| K5 | fingerprint 12 hex | KILLED |
| K6 | fingerprint 20 hex | KILLED |

Counted from the table: 12 run, 12 KILLED, 0 SURVIVED, 0 NOT APPLIED. The builder's 4 mutants are among these. HIGH.

CONDITIONS
C1 (decision for Don, carried by the builder) move the cron lines and the runbook examples to `--verify-token-env`, and make it the default when the old placeholder is deprecated; until then F3 stays open on every deployed schedule.
C2 (follow-up card) remove or gate `--allow-plaintext` in tools/phase_g_check.py the same way; run the verifier with a minimal environment (the renew token variable plus PATH and what it needs) instead of the whole inherited one.
C3 (standing gate) GX10 16/16 and CI on this exact head, including the whole test_renew_token.py (not run by me, about 185 subprocess tests); not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
The full test_renew_token.py and test_estate_probe.py, GX10 / Linux, CI, a real verifier with a secret in the environment.

CONCLUSION
F4 and F5 are closed as measured: estate_probe has no cleartext override (and the check refuses it with the flag gone), and `--check` prints 16 hex at all four sites, with 12 of 12 mutants killed, 111 and 6 tests passing, anchors green, identity correct. F3 is delivered as an opt-in flag with the default unchanged, so the exposure stays on every schedule until cron moves. PASS WITH CONDITIONS: C1 Don's, C2 a follow-up, C3 the gate.
