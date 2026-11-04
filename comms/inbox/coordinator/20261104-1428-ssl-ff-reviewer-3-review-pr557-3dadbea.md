# Review PR 557 @ 3dadbea0b6e63ead437c02b24c7c1fd3eea5e48d (rebuild of #408, public-safety follow-up to C-758) - reviewer ssl-ff-reviewer-3

**VERDICT: BLOCK on head 3dadbea0 until Don re-rules three lines. Everything else in the PR passes. UNVERIFIED (cloud, no GX10).**

## Blocking finding (HIGH, read from the diff and from main's history)
- F-R557-1 BLOCK: this head undoes a ruling already on main. Main commit 793481f3, "Keep the company's own contact in the plugin and marketplace metadata and the invoicing skill (Don 2026-11-03, Q-86 F1); client mailboxes stay scrubbed", changed exactly three lines: the owner contact in `.claude-plugin/marketplace.json`, the author contact in `plugins/field-agent/.claude-plugin/plugin.json`, and the Interac e-Transfer mailbox line in `agents/ssl-invoicing-agent/SKILL.md`. PR 557's diff against main changes the same three lines back to a placeholder (marketplace.json line 5, plugin.json line 8, the e-Transfer line in the invoicing skill). Same defect I reported for the old head PR 408. If Don wants the placeholders, the PR stands; otherwise those three hunks must be dropped. I do not know Don's current intent beyond the 2026-11-03 text.

## Objections first
1. Two scrubs can pull in opposite directions: client names, client mailboxes and customer codes (scrubbed on purpose, "client mailboxes stay scrubbed") versus the company's own contact (kept on purpose). The structural guard in this PR allows the project's own domains and reserved example domains, which agrees with the ruling, but the PR's own content edit does not.
2. The new test guard is structural and relies on a placeholder shape; a real value of fewer than 5 digits, or one that is not a mailbox, passes. By design (the file says so).
3. The bank-transfer line (institution, transit, account number) is on main today in the invoicing skill; this PR replaces it with placeholders. That scrub is right for a public repository and is NOT part of the 793481f3 ruling (which names the e-Transfer mailbox line only). I did not print any value. Don should confirm that the bank line scrub is wanted.

## Facts (HIGH unless tagged)
- Head fetched via refs/pull/557/head = 3dadbea0; 8 commits; base is origin/main 97dcfec1 (main has since moved one unrelated commit); author AND committer on all 8: Don Hagell <13129187+dhagell@users.noreply.github.com> (lineage fine: unlike PR 408 this is a real rebuild).
- 9 files, +147 -29: two skills, `manifests/ssl-timekeeping-agent.yaml`, `tools/field-rest.ps1` (one path), `STATE.md` (scene4.mp4 line), `integration/video/out/scene4.mp4` deleted (520735 bytes), the two plugin/marketplace JSON files, and `tools/tests/test_skill_public_safety_c1088.py` (+118).
- Baseline unmutated on the head: the guard file 24 passed, 1 skipped (the skip is the optional external deny-list test).

## Mutants (the guard file only; my mutants edit the invoicing skill or the guard; files restored, clean)
| Behaviour | Rows | Result |
|---|---|---|
| injected value must turn the guard red: 5-digit number, external mailbox, lookalike domain, value hidden in a placeholder, long digit run in a placeholder, subdomain of an external domain (I1-I6) | 6 | 6 KILLED |
| clean text must stay green: own-domain mailbox, port after a host, port after a placeholder, reserved example domain (K1-K4) | 4 | 4 clean (no false red) |
| the guard itself weakened, with the matching bad input in place: dot boundary removed, digit run 7, own domain dropped (W1-W3) | 3 | 3 detected (the guard's own corpus tests went red) |
Totals counted from the table: 6+4+3 = 13 rows; 6 killed, 4 clean, 3 weakened-guard detected; 0 survivors, 0 false reds.

## Findings
- F-R557-2 LOW: the video file removal is correct against STATE.md (the line now says it is not committed), but history still holds the 520 KB binary; removal from the tree does not remove it from a public history (not a defect of this PR).
- F-R557-3 LOW: the guard test's optional deny-list needs `FIELD_PUBLIC_SAFETY_DENYLIST`; CI never runs it (the test says so); I did not run it.

## Conditions
1. Don rules on F-R557-1 (three hunks), and on the bank-line scrub in objection 3.
2. If kept, GX10 16/16 and CI on this head rebased on current main.
