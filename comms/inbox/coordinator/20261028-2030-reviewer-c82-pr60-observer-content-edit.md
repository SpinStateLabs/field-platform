# C-82: PR 60 fix/observer-witness-content-edit at c71c8be (C-36) (teammate-don-reviewer, 2026-10-28) - PASS with two LOW

Base main 75a84c8, 0 behind / 1 ahead, one commit, author and committer Don Hagell <13129187+dhagell@users.noreply.github.com>. VERIFIED on the GX10 (fresh clone ~/ff-work/wt-fieldrev-60, Python 3.12.3, CI=true, no network, no DB port). I did not write the fix; it fixes my C-34 part 2 finding 1.

## The change (sealed-ledger operator_observer.py `_observe_self_witness`, +13/-5; tests +34/-1)
The validated file sha prefix joins the change key as the 5th element (`key = (fmt, gen, rows..., sealed_state, sha)`), and the `operator.registry_slots_changed` payload gains `previous_registry_sha256_prefix` (`previous[4]`). The sha is re-validated (16 lower-hex or None) before it is ledgered; no raw value reaches the ledger.

## Verified
- Original probe re-run on the PR head: slots_changed events: first=1, content-only edit (new sha, same generation and fingerprints)=2 (was 1), generation bump=3 (was 2); the second event carries `previous_registry_sha256_prefix` and `changed_operator_ids: []`. The finding is fixed.
- Tests: observer files (c6, c6_fetch, c6_serve, r2) 73 passed (71 + 2 new: `test_a_content_only_edit_is_witnessed_when_only_the_file_sha_changes`, `test_a_missing_or_malformed_sha_is_a_change_to_none_and_is_never_ledgered_raw`; the first-event payload test updated for the new field); full sealed-ledger suite 650 passed, 4 skipped (648 + 2).
- Mutants (5, all KILLED): K1 sha out of the key (2 red); K2 `previous[3]` instead of `previous[4]` (2 red); K3 sha regex check dropped so a raw value is ledgered (1 red); K4 previous sha always None (1 red); K5 sha compared only at startup (9 red).
- Consumers: no other code reads this event (grep: the observer module only); no ledger-side schema for `operator.registry_slots_changed`, so the new field breaks nothing on the PR head.

## Findings
1. LOW (docs): the module docstring that lists the payload (operator_observer.py ~L55-60: `{format, generation, rows, changed_operator_ids, sealed_key_changed}` "at the first valid parse and on every change") was not updated for `registry_sha256_prefix` and `previous_registry_sha256_prefix` or for "a bytes-only change is an event". Update it and the sealed-ledger README observer table.
2. LOW/INFO (by design, stated in the PR): the event says bytes changed, not WHAT: `rows` and `changed_operator_ids` are empty for a scopes/auth/expiry edit, so an auditor still has to diff the files. Acceptable; if a content digest of the non-key fields were added later (roster digest `operator_roster_sha16` already exists in `rotation_state`), the event could say which class changed. Not required.
3. INFO: any byte change (whitespace, comment-free reformat) is an event; combined with rotator writes this is one event per operators-file write, same as the generation events before.

## Verdict
PASS. NOT verified: a live estate; the interaction with the dead-man/R6 audit tools that do not exist yet.
