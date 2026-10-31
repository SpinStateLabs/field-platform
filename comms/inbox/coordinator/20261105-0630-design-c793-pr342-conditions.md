VERDICT: C-793 PASS WITH CONDITIONS on 697b8ec62b8a22729838716645ea94ede363dcff (PR 342, was b03bf8d; three C-726 commits and one C-607 doc commit since). Most of what my C-693 and C-743 raised is closed or smaller. The tree still holds personal-path text on allowlisted files, the history question is open, and 10 of 63 evasion spellings in my probe are still not flagged (17 at b03bf8d). No value printed; files and counts only. UNVERIFIED on any estate; read-only.

## C-619 / C-693 / C-743 conditions and state
1. Guard scans test files and fails on unreadable or oversize files: closed (tests pass: 144 passed, 2 skipped across the guard, the Windows-pin and the two PowerShell test files). HIGH.
2. Allowlist entries each carry a reason, and an entry without one is refused (C-726): closed. The file has 18 lines; none lacks a reason column; the format is `path::class = count | reason` and the guard test fails on a missing or short reason (MIN_REASON = 20 characters). HIGH.
3. Windows-style personal paths: reduced from 19 hits in 3 files (C-743) to 3 hits in 1 file, all allowlisted. The PowerShell tests no longer hold a personal path (commit 82c73ab). CLOSED for two of three files. HIGH (my scan, approximate patterns).
4. Unix-style personal paths: UNCHANGED: 100 hits in 4 files (the compose-pin test 84, the GB10 compose file 14, the deploy runbook 1, the deploy-docs test 1), all allowlisted as functional defaults needing an operator decision. The commit 697b8ec changes two lines of the runbook so it names no workstation beside the path replacements. OPEN. HIGH.
5. Private-range addresses: 24 hits in 9 files (28 in 10 before), all allowlisted as fixtures. Whether any is an estate address is not judged and not printed. OPEN as before.
6. Webmail: 0 hits (unchanged). History: still carries the earlier values; a decision for Don (C-693 F-C693-2). OPEN.

## Objections first
1. THE GUARD STILL MISSES 10 SPELLINGS OF MY 63 (made-up values only; probe pushed beside this note). At b03bf8d 17 were missed. Still not flagged: IPv6 unique-local forms (`fc`, `fd` ranges), IPv6 link-local, an address written as a decimal integer and as a hex integer, the 169.254 link-local range, an mDNS host name, an obfuscated at/dot mailbox ("zed at example dot com" style), a percent-encoded Windows path, and a `~user` path. Some are arguably not personal (link-local), and a decimal or hex address is an exotic spelling; the unique-local IPv6 range, the `~user` form and the obfuscated mailbox are the ones I would add. MEDIUM (observed).
2. THE ALLOWLIST IS STILL THE MECHANISM (C-743 objection 3): 100 Unix-path hits sit behind 4 allowlist lines; a new hit in any of those four files is invisible unless the count changes (the guard compares counts: "Must equal the scan"), which does catch an added hit in a listed file but not a replaced value. MEDIUM.
3. THE SCAN FLOOR IS A FILE COUNT. `MIN_FILES = 600` (test_public_safety_c560.py:150) is pinned near the repository size so a collapsed `git ls-files` fails; it moves with every added or removed file batch. LOW.

## Steelman
The C-693 findings were taken: reasons required, relocated home roots and UNC admin shares and bracketed or encoded mailboxes added, blindness floor and every provider and top-level domain pinned, Windows-only test files cleaned, a new test pins the Windows couplings without PowerShell.

## Where in the tree (counts by file, no values)
Unix-style personal paths: tools/tests/test_compose_static_pins.py (84), integration/demo/docker-compose.gb10.yml (14), docs/runbooks/v1.2-deploy-rollback.md (1), tools/tests/test_deploy_docs.py (1). Windows-style: one test file (3). Private addresses: 9 files, 24 hits (fixtures in defence-shield and tools tests, two manifests, two others). All on the allowlist. HIGH.

## What I did NOT do
- Did not judge any address or path as estate or personal.
- Did not scan history (the decision on rewriting it is Don's).
- Did not scan binary or oversize files the guard skips.
