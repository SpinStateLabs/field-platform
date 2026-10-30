# C-693: delta review of PR 342 at b03bf8d8520826d4100e64e31d06f7672631cc20 (public safety), Lane 10

VERDICT: PASS WITH CONDITIONS on b03bf8d8520826d4100e64e31d06f7672631cc20 (one commit on 4ea4db6, the head of my C-619). The guard now scans test files, fails on an unreadable or oversize candidate, and covers more spellings (4 of the 5 C-619 findings are closed in the guard). The personal-path sites in test files are now VISIBLE to the guard but are still in the tree, listed in the allowlist, and history is unchanged. THIS REPORT PRINTS NO PERSONAL VALUE: class, file and count only; names are described by length. Confidence HIGH (counts run); the PR text is UNREADABLE here (no GitHub access): UNVERIFIED.

## ASSUMPTIONS
1. The delta is tools/tests/test_public_safety_c560.py (+125 -27) and tools/tests/public_safety_allowlist.txt (+18).
2. "Personal path" is a user-profile path with a non-placeholder account name; estate accounts and endpoints are a separate class in this lane's rules.

## Objections first
1. Closing the blind spot by scanning tests produced an allowlist that RATIFIES the sites it found: `tools/tests/test_ssl_renewal.py` (windows-user-path x12, private-ipv4 x4), `tools/tests/test_field_rest_secret.py` (windows-user-path x4), `tools/field-rest.ps1` (windows-user-path x3), plus a test fixture file with 108 unix-home-path sites (`test_compose_static_pins.py`), 9 private-ipv4 sites in `defence-shield/.../test_allow_ip_c240.py` and smaller counts elsewhere. A scan that lists a site and then permits it keeps the value public. My own scan finds 40 non-placeholder user-path sites in 5 files: 19 carry the same 5-character account name (the PowerShell shim 3, test_field_rest_secret 4, test_ssl_renewal 12), the rest are the one-letter and estate-account fixtures of the compose-pin test. I did not print or compare any name. HIGH.
2. Git history is unchanged: every value ever committed stays public. Rewriting history is a decision for Don (C-619 F-C619-2). Nothing in this PR changes it.
3. The guard is still a list of spellings; my 63-case probe now has 17 reds (was 35).
Steelman: the guard is stricter in every dimension I asked for, and its allowlist is explicit and must equal the scan in both directions, so any new site fails.

## Results: the five C-619 conditions
- F-C619-1 (test files exempt): CLOSED in the guard (tests are scanned; the file that builds the patterns from parts exempts itself only). 71 tests pass. The sites it found are allowlisted (objection 1), so the TREE is not cleaner.
- F-C619-2 (history): OPEN, for Don.
- F-C619-3 (functional defaults still allowlisted, wanted at zero): OPEN: `tools/field-rest.ps1` x3, `integration/demo/docker-compose.gb10.yml` x14 and `docs/runbooks/v1.2-deploy-rollback.md` x1 (unix-home-path), `manifests/ssl-invoicing-agent.yaml` x2 and `manifests/ssl-timekeeping-agent.yaml` x2 (private-ipv4) are unchanged.
- F-C619-4 (spellings): mostly CLOSED. Now flagged: WSL and Git Bash forms, lower- and upper-case `users` and drive letters, the extra webmail providers, CGNAT 100.64/10. Still not flagged: `/var/home` and `/export/home` and `/data/home`, `~name`, a UNC admin share, percent-encoded paths and addresses, an HTML-entity at-sign, obfuscated addresses (`at`/`dot`, `(at)`), decimal and hex integer IPs, `.local` hostnames; IPv6 unique-local and link-local are by the guard's definition. LOW-MEDIUM.
- F-C619-5 (unreadable or oversize candidate skipped): CLOSED: such a file now FAILS the scan (tests `test_an_unreadable_or_oversize_candidate_fails_the_scan` name `bad.txt`, `big.txt`, `gone.txt`).
- Public-safety scan of the delta itself: the added test lines use made-up names and the allowlist holds paths, classes and counts, no values. Commit identity: the repository's no-reply form (checked in C-619).
- Where a personal path still sits in the tree (class and file only): `tools/field-rest.ps1`, `tools/tests/test_ssl_renewal.py`, `tools/tests/test_field_rest_secret.py` (windows-user-path, one 5-character name); the compose-pin test and the GB10 compose default (unix-home-path, an estate account); two manifests and the defence-shield and other tests (private-ipv4, estate or fixture addresses).

## Findings
F-C693-1 MEDIUM: replace the values in `test_ssl_renewal.py` and `test_field_rest_secret.py` with placeholders (the tests exercise a path SHAPE) and in `tools/field-rest.ps1` with an environment-derived default; then delete those allowlist lines. Those 19 sites are the same value the PR set out to remove.
F-C693-2 MEDIUM (Don): history rewrite yes or no (unchanged).
F-C693-3 LOW-MEDIUM: add `/var/home`, `/export/home`, `~name`, UNC admin shares, percent-encoding and the obfuscated-address spellings, or state in the docstring that deliberate obfuscation is out of scope.
F-C693-4 LOW: forbid allowlisting a site in a file whose job is to be a fixture without a recorded reason per line (the allowlist is `path::class = count`: no reason).

## What I did NOT do
Did not read the PR title, body or comments. Did not compare any name with the removed value or with any person. Did not examine other branches, images or PDFs. Did not edit the PR.
