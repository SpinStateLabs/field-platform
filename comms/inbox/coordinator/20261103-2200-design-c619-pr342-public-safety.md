# C-619: review of PR 342 (personal paths and a mailbox replaced by placeholders, plus a guard test), Lane 10

Reviewed: PR 342 head 4ea4db6 (25 files, +317 -124; the guard is tools/tests/test_public_safety_c560.py with tools/tests/public_safety_allowlist.txt). HIGH CARE, public safety. THIS REPORT PRINTS NO PERSONAL VALUE: findings are given by class, file and count only; names are described by length. Probe: 20261103-2200-design-c619-public-safety-evasion-probe-test.py (made-up names only; `GUARD=<checkout>/tools/tests/test_public_safety_c560.py python -m pytest -q`).

VERDICT: PASS WITH CONDITIONS on 4ea4db6. The PR removes the values it names from non-test files and the guard (34 tests) passes. The guard has a structural blind spot, test files, and a personal Windows path of the same non-placeholder name still sits in two TEST files (16 sites) in the public tree. Public git history still holds every removed value. Confidence HIGH (counts run); the PR TEXT could not be read (no GitHub access in this session): UNVERIFIED.

## ASSUMPTIONS
1. "Personal" means an account name in a user-profile path, a consumer mailbox, or an address the owner does not publish; estate endpoints are in scope under this lane's rules (no estate addresses).
2. The guard's job is to keep NEW values out; removing old ones from history is a separate decision.

## Objections first (failure conditions)
1. The guard skips every test file (`_is_test_file`: any path with a `tests` directory, `test_*` or `conftest.py`): 325 of 690 tracked files, 47% of the tree, are never scanned. Evidence it matters: my scan with the same Windows-path class over the whole tree finds 16 sites in `tools/tests/test_ssl_renewal.py` (12) and `tools/tests/test_field_rest_secret.py` (4), each with a non-placeholder 5-character account name (the same shape and length at all 16; I did not print it, and did not compare it with the removed value). They are invisible to the guard by construction. HIGH.
2. History: the values the PR removes are still in the 412 commits of public history (a count-only `git grep` of an old commit still finds the Windows-path class in four files). Replacing text in the tree does not unpublish it. Whether to rewrite history is a decision for Don (it changes every commit id); I recommend the owner decide knowingly. HIGH.
3. The allowlist ratifies functional sites that are themselves public estate or personal detail: private-IPv4 x4 (two manifest files, endpoints), unix-home-path x15 (14 in the GB10 compose default plus 1 in a runbook: an estate account's home directory), windows-user-path x3 (tools/field-rest.ps1, a shim default). The allowlist can only shrink, but nothing forces it to. MEDIUM.
4. The guard is a list of spellings again (the bind-source pattern). My probe of 63 spellings: 28 behave as intended, 35 are not flagged (see section 3); some of those are by the guard's own definition (link-local, IPv6), the rest are real gaps.
5. Files the scan cannot read are skipped silently: binary suffixes, files over 2 MB, non-UTF-8 text. Today none are affected (0 non-UTF-8 and 0 oversize among scanned candidates; 2 binary-suffix files), so this is future risk.
Steelman: the guard is built from parts so its own file holds no matchable value, requires the allowlist to equal the scan both ways, and has a non-blindness test; it closes the leak that was found.

## Results
- Non-test files: the PR's own scan is clean except the 5 allowlist lines above. My broader classes (case-insensitive `users`, WSL and Git Bash `/mnt/c/Users/X` and `/c/Users/X`, `/var/home`, CGNAT 100.64/10, link-local 169.254, IPv6 unique-local, more webmail providers, obfuscated addresses, `.local` hostnames) found NOTHING new in non-test files; they found link-local 169.254 in 6 files (kill-switch SSRF tests and docs: the cloud metadata address, legitimate) and `.local` names in 2 test files. So the spelling gaps are future risk, not present leaks.
- Secret shapes (counts only; the repo's own 10 redaction patterns plus mine): every hit is in a test file or fixture (private-key blocks in 9, sk-style strings in 9, anthropic-style in 4, URLs with a password in 4); none in a non-test file. I did not judge that each is made up (they sit in key-handling tests and fixtures); 0 in non-test files is the finding.
- Commit identity: author and committer are the repo's noreply identity; the commit carries the session trailer (the same policy question as in C-499).
- The guard test file: 34 passed on the head.

## Spelling gaps (probe; the guard does NOT flag these)
Real, plausible for this project: WSL and Git Bash forms (`/mnt/c/Users/<n>`, `/c/Users/<n>`: the lookbehind `(?<![\w.])` blocks them); lower-case or upper-case `users` and a lower-case drive (the class spells `Users` case-sensitively); CGNAT 100.64/10 (overlay-VPN addresses, which are estate addresses but not RFC 1918); webmail providers outside its list (`googlemail`, `live`, `msn`, `aol`, `gmx`, `yandex`, `qq`, `me`, `pm`, `hey`, `fastmail`, `zoho`). Lower value: `/var/home` and `/export/home`, `~name`, percent-encoded paths, obfuscated addresses (`at` / `dot`, `(at)`, `%40`, `&#64;`), decimal or hex IP spellings, `.local` host names. By definition of the class and fine: link-local, IPv6.

## Findings
F-C619-1 MEDIUM (blind spot): scan test files too. The guard builds its patterns from parts so it needs only itself exempted; move test-file values to placeholders, or allowlist them by count like the rest. This also catches the 16 sites above.
F-C619-2 MEDIUM (decision for Don): history. Either accept that removed values stay public, or plan a history rewrite; the PR cannot do this.
F-C619-3 MEDIUM-LOW: replace the functional defaults with environment-derived values (`$HOME`, a variable with no personal default) so the allowlist reaches zero; the PowerShell shim and the compose caller-keys default are the cases.
F-C619-4 LOW-MEDIUM: add the WSL and Git Bash forms, case-insensitive `users`, CGNAT, and the extra webmail providers to the classes; one pinned case per spelling from the probe.
F-C619-5 LOW: fail the scan (not skip) on an unreadable or oversize candidate.

## What I did NOT do
Did not read the PR title, body or comments (no GitHub access): any personal value there is UNVERIFIED. Did not compare the test-file names with the removed value. Did not examine branches other than the PR head and main, images, or PDFs. Did not print any value. Did not edit the PR.
