VERDICT: PASS WITH CONDITIONS on 5955870ee06647b839e27406f9560e4577164f5f  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-879, PR 325 (field-core, claude-approver, compliance-crosswalk: drop unread constants and unused imports) after C-837 (PASS WITH CONDITIONS on 5955870). The PR head is still 5955870 (fetched this session): no commit since C-837. This SHA only.

OBJECTIONS FIRST
1. Every removed name has no reader anywhere. The five removals are: `MAX_OPERATOR_LEN` and `MAX_KEY_LEN` (operator_auth.py), the `re` import (validation.py), `AgentMap` from the import line in claude_approver/core.py, and `AgentNotRegisteredError` from the function-level import in compliance_crosswalk/api.py. Checks on the head, whole tracked tree and all file types (`git grep -w`): MAX_OPERATOR_LEN and MAX_KEY_LEN: zero hits; AgentMap: only its definition and uses inside claude_approver/config.py, none in core.py or elsewhere (no re-export: `core.AgentMap` is not referenced); AgentNotRegisteredError: defined in field_core/clients.py and imported by other services' own import lines (conformance-sentinel, delegation-authority, kill-switch, incident-replay, lifecycle-manager) but not used in compliance-crosswalk/api.py after the edit; `re` in validation.py: no `re.` use, no `validation.re` reference anywhere. String lookups: no `getattr(..., "NAME")` or quoted-name reference for any of the five; no `__all__` in the four edited modules; no `from x import *` in the tree. AST check on each edited file: none of the five names is used as a Name or Attribute, and none appears as a word in a string literal. Confidence HIGH for the tracked tree. NOT VERIFIED: callers outside this repository (the plugin repositories, estate scripts), which no tree search here can see.
2. C-837's three conditions are all unchanged at this head, since nothing moved:
   - F-C837-1 (LOW-MEDIUM): the removal date "2027-01-31" at operator_auth.py:518 and :548 is a comment; the test checks only a date-shaped string. Re-run: changing both dates to a past date (2020-01-31) or an impossible one (2027-99-99) leaves test_operator_auth.py at 62 passed. OPEN. The date is also the builder's proposal, not a recorded ruling.
   - F-C837-2 (LOW): `_PASSKEY_LABEL_RE` shares the `{1,64}` literal; its bound is unpinned: `{1,63}` and `{1,65}` both survive (62 passed each). OPEN. (The operator-id and key caps are pinned: `{1,63}`, `{1,65}`, key `{1,255}`, `{1,257}` all go red, 4 of 4.)
   - F-C837-3 (LOW): the deprecated helpers `strip_reserved_unless_asserted` and `reject_reserved_event_type` have no caller outside their definitions and tests (not re-grepped by me beyond the AST/grep above, which found none in the edited modules). OPEN; the "keep" decision keeps dead code with a date.
3. Tests at the head: field-core 1122 passed 1 skipped; claude-approver 282 passed; compliance-crosswalk 353 passed 5 skipped.
4. The unused-import removals are behaviour-neutral: removing an import that no code in the module reads cannot change behaviour unless something else reads it through the module (checked in objection 1) or the import had a side effect (the removed names are classes and constants in modules that are imported anyway for other names: `claude_approver.config` and `field_core.clients` stay imported on the same lines).

ASSUMPTIONS
A1 Card scope: each C-837 condition against the head; each removed name has no reader anywhere (tools, tests, docs, string lookups). A2 The tracked tree is the whole repository.

REASONING / CHECKS
- `git grep -w` for the five names, a search for `validation.re` and quoted-name lookups, `__all__` and star-import searches, and an AST walk of the four edited files, all on a scratch tree of the head (removed afterwards; nothing committed).
- Mutants (each restored): operator-id cap 63 and 65 KILLED; key cap 255 and 257 KILLED; passkey label cap 63 and 65 SURVIVED; past removal date and impossible removal date SURVIVED. Four killed, four survived.
- Commits: three, author and committer Don Hagell no-reply. Diff scan of the PR's source and test changes: no address, flag value, credential or deploy status.

CONDITIONS
C1 (non-blocking) Parse the removal date in the test and assert it is valid (and, for a control, that it has not passed) (F-C837-1).
C2 (non-blocking) Pin the passkey-label bound on both sides (F-C837-2).
C3 (non-blocking) Decide the two deprecated helpers: delete once their tests are ported, or record the date as a ruling (F-C837-3).

NOT VERIFIED
GX10 full set, CI by run id, readers outside this repository, the other 13 services' suites.

CONCLUSION
The five removals are safe: no reader in the tracked tree by name, by attribute, by string or by re-export. The C-837 conditions are open as before because the head did not move. PASS WITH CONDITIONS, none blocking. UNVERIFIED.
