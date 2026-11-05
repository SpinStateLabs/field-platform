# Reviewer report: PR 710 (S6-9 sealed-ledger: witness head and caller id use fullmatch), reviewer ssl-ff-reviewer-5

**Head reviewed: cde9e9cfb8aede6d73c7186e7fd92836714b5b2d** (1 commit on ebb027a2, main is now aab217d3; services/sealed-ledger/src/sealed_ledger/store.py 1 line, witness.py 2 lines, new tests/test_hex_and_caller_id_fullmatch.py +73). Run UNVERIFIED (cloud, no GX10). Not run: CI, the other services. The comms inbox has a builder note for this item (builder-1, 20261104-2105, "s6-9 ledger newline"); it is not a Lane O builder note. Taken after `dispatch.sh next` returned it.

**VERDICT: PASS WITH CONDITIONS** (the fix is correct and pinned for what it claims; 3 real survivors in nearby behaviour, 2 equivalent; a same-class pattern remains in 7 other call sites; no conflict; identity clean).

## Objections first
1. THE CLASS OF BUG IS WIDER THAN THIS PR. `re.match(r"^...$")` lets one trailing newline through `$`; the three sealed-ledger sites are fixed here. I scanned services, packages and defence-shield (non-test sources) for `^...$` patterns used with `.match` or `.search`: 7 call sites remain, all in field-core: `_OPERATOR_RE.match` (operator_auth.py:1356, the operator-id header), `_KEY_RE.match` (operator_auth.py:336 and 1358, the key), `_SHOWABLE_FLAG.match` (operator_auth.py:265), and in alerts.py `TOPIC_RE.match` (lines 339 and 344) and `_TOKEN_RE.match` (333). 26 other anchored patterns already use `fullmatch`. Exploitability, read from the code: line 336 strips the key first (a trailing newline is gone before the test), HTTP header values do not carry a raw trailing newline through a normal server (general knowledge, MEDIUM), and the alert values come from env or a file; I did not trace every path, so I do not claim a live hole. HIGH on the pattern, LOW-MEDIUM on harm. F-PR710-1.
2. The type check `not isinstance(head, str)` in `parse_head` is not pinned (below): a JSON `head_hash` that is not a string reaches the regex as a non-string, and without the check it would raise `TypeError` from a function whose contract is `WitnessError`. The same check in `check_anchor` is pinned (by an existing suite test, not by the new file).
3. The caller-id rule is now exact, but the character set is only half pinned (c9, c10 below). The id becomes part of a key file name (`<id>.pub.pem`), so what the rule admits is a file-name decision.

## Identity and base
Author and committer = Don Hagell <13129187+dhagell@users.noreply.github.com>. Main's changes since ebb027a2 do not touch these files; `git merge-tree` against current main: no conflict. HIGH.

## Mutants (real lines; scratch worktree detached at the head; relative PYTHONPATH). Stage 1 = the new file (baseline 0 failed, 37 passed); a survivor goes to stage 2 = the whole sealed-ledger suite (baseline 1 error, 839 passed, 5 skipped; the one error is identical on main aab217d3-era code in this sandbox, so it is subtracted and a stage 2 kill needs more than that)
Groups (killed / applied): `parse_head` (back to match, to search, type check removed) 2/3 (survivor p3); `check_anchor` (match, search, type check removed, message text) 4/4 (a3 killed by the whole suite only); `_HEX64` (length 63, 65, 63 to 64, 64 to 65, upper case, alphabet drops f, `$` removed, `^` removed) 6/8 (h7 and h8 survive: equivalent under `fullmatch`); caller id (match, search, type check, max 64, max 62, leading hyphen, no hyphen, upper case, underscore, dot, invalid id raises) 9/11 (survivors c9, c10).
Totals COUNTED FROM THE LOG: 3 + 4 + 8 + 11 = 26 mutants applied; 21 killed (19 by the new file, 2 only by the whole suite), 5 survived (p3, h7, h8, c9, c10); none failed to apply. h7 and h8 are equivalent (HIGH: under `fullmatch` the anchors are redundant), leaving 24 non-equivalent, 21 killed, 3 real survivors.

## Survivors
- p3 (LOW-MEDIUM, HIGH it survives the whole suite): non-string `head_hash` into `parse_head`; add a case with `null` and a number.
- c9 and c10 (LOW, HIGH it survives): an underscore or a dot in a caller id is accepted by the mutant and the tests never send one; the refused list has `/`, space, newline, `A`, `-a`, 64 characters but not `_` or `.`. F-PR710-2.
- h7, h8: equivalent (the rule is enforced by `fullmatch`, so the anchors in the pattern text are now decoration; keeping them is harmless).

## Findings
F-PR710-1 LOW-MEDIUM: the 7 remaining `.match` sites (objection 1), a one-line change each, in a NEW PR with a test per site. F-PR710-2 LOW: add `null`, a number, `a_b` and `a.b` to the refused cases (p3, c9, c10).

## Conditions
None block. Coordinator: GX10 16/16 and CI on this exact head.
