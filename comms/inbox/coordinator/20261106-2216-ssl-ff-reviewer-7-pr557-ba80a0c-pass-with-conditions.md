# Review PR 557 (rebuild of #408: public-safety placeholders in the two SSL agent skills, C-1088) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `ba80a0c63668d29cf380083a80afe144d89b6b0b`.
Conditions: C1 (process, merge-blocking by the precedent on PR 308, 795 and 821): 7 of the 9 commits carry `Co-Authored-By: Claude Fable 5.1` trailers (the standing rule is never Fable); the coordinator must rule or re-cut the trailers. C2 (decision for Don, not code): the PR deletes `integration/video/out/scene4.mp4` (520,735 bytes) from the tree. A deletion does not remove it from git history of a public repository; if the file is removed because of what it shows, only a history rewrite closes that, and I cannot tell from the sources why it goes (the PR text says only "drop scene4.mp4"). C3: CI and the coordinator's GX10 run on the landed head.

## Objections first
1. The guard test checks only the two SKILL.md files (and the optional external deny-list). The same PR also edits `manifests/ssl-timekeeping-agent.yaml` and `tools/field-rest.ps1`; a leak there is not guarded (LOW; my scan of the resulting files found none).
2. The invoicing skill still names the company's payment mailbox (`Interac e-Transfer to don@spinstatelabs.ca`, line 98). That is deliberate (the last commit, "keep the company's own contact"; the guard allows the project's own domains `spinstatelabs.ca` and `.com`). A payee mailbox in a public file is a decision for Don, not a defect I can call.
3. The rebuild was not a clean cherry-pick (three conflicts resolved by judgement, main's C-1130 mailbox tokens kept, the PR's fuller placeholders taken in the invoicing skill); the PR says so. Commits 4-8 apply identically (its range-diff).

## Checks (HIGH, run by me)
- Identity: 9 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 9 (the PR says an earlier branch carried two committers `dhagell <>`; this one has none); .github/: 0 files. 7 files: STATE.md (+1/-1), invoicing SKILL (+7/-7), timekeeping SKILL (+15/-15), the manifest (+2/-2), field-rest.ps1 (+1/-1), the guard test (+118), scene4.mp4 deleted. Based on 97dcfec1; main is 250154d3; a trial merge into current main is clean.
- Scan of the resulting skill, manifest and script files for identifiers (mailboxes, a five-digit-plus run, phone-like numbers, named client portals, account words): only `don@spinstatelabs.ca` (the company's own, objection 2) and the example-domain token `contact-4@example.com`; no client name, customer code, portal host or personal mailbox remains in the placeholdered text.
- Tests on the exact head (Windows): test_skill_public_safety_c1088.py 24 passed, 1 skipped (the skip is the optional external deny-list, `FIELD_PUBLIC_SAFETY_DENYLIST`, which the repository correctly does not carry).

## Guard mutation test (leaks injected into the two skills, one at a time; counted from the table)
| # | injected text | result |
|---|---|---|
| S1 | a personal gmail mailbox (timekeeping skill) | KILLED |
| S2 | a mailbox on a lookalike of the own domain (no dot boundary) | KILLED |
| S3 | a mailbox on the own domain (control) | passes, as designed |
| S4 | a five-digit project or customer code | KILLED |
| S5 | a four-digit number (control) | passes, as designed |
| S6 | a client name and number hidden in angle brackets | KILLED |
| S7 | a placeholder with a number inside | KILLED |
| S8 | a personal mailbox in the invoicing skill | KILLED |
| S9 | a subdomain of an example domain (control) | passes, as designed |
| S10 | a port after a host (control) | passes, as designed |
Totals: 10 injections: 7 leaks, all 7 caught; 3 controls that the rules allow, all 3 pass; 0 unexpected results (7+3 = 10).

## Not verified
CI/GX10; Linux; the content of scene4.mp4 (so whether a history rewrite is needed); the external deny-list (it lives outside the repository by design).
