# C-1064: conditions on PRs 372, 373, 374, 377, 379; GX10 results for C-1060 and C-1061 (builder Lane 12)

Same method as C-1061: latest reviewer report per PR; closed items pushed to the SAME branch, one commit per finding; no rebase.

| PR | head now | what I did |
|---|---|---|
| 372 | unchanged (1b8f9e3f) | C-884 C1 asks to pin register's type-name-only message: it IS pinned at this head (`test_register_names_only_the_kind_of_failure`, exact string, `__cause__` and `__context__` None; Lane 1's C-855 C2). C2 (ruling on the BLOCK relay; a size cap on SDK reads) is Don's/carried; C3 (PR 326 versus PR 372) is the coordinator's. Nothing to change. |
| 373 | 8bca5f65 (was 8c3cfb5e) | C-856: F-C856-1 decided and pinned: the /totals 422 for a bad instant no longer repeats the caller's value (fixed text "since is not an ISO 8601 instant"; the value is unbounded caller text); the 404 keeps naming the path agent id exactly as /status does, now pinned against /status. F-C856-2: a space-padded `since` is refused, pinned (a `strip()` mutant KILLED). Tests red first (the echo), then the change; spend-governor suite 281 passed, 4 skipped. Mutants: the 422 repeats the value KILLED; since stripped KILLED. F-C856-3 (INFO: accepted ISO formats depend on the Python version; floor 3.11) not pinned. GX10 FULL run on 8bca5f65 below. |
| 374 | b97d35fc | Closed earlier (notes 20261106-0100 and 20261105-2000); open there: the equal-to-read-key refusal (after PR 369 merges), the unbuilt wiring and counter, the ENFORCE rule (Don). |
| 377 | 4292a6ae (was dfceabcf) | C-875: C1 line ranges: the runbook now cites the sender (`alert_test_cmd`) and the classes (`CLASSES`, six production entries and one `test` entry) by NAME, not by line (so they cannot drift); C2: the deferral cites Don's ruling C-552 with C-760 as the docs card. C3 is for C-760 itself. Docs only: `test_runbook_pins_c465` and `test_deploy_docs` 43 passed locally; a LIGHT run per PROTOCOL (docs only), CI runs the full set. |
| 379 | unchanged (f958cab8) | C-1006: the three conditions are the coordinator's or Don's (merge with PR 342 for the workstation name and paths; decide the :484 sentence; CI on the new head). No change to the file from me. |

## GX10 results (full 16-suite runs, 0 failed|error each, on the exact heads)
- C-1060: PR 331 543fe639 (reported in 20261031-1700).
- C-1061: PR 336 853a5b1e; PR 344 22d04601.
- C-1064: PR 373 8bca5f65.
