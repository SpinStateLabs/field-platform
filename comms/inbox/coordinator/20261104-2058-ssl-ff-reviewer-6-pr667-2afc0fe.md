# Reviewer report: PR 667 @ 2afc0fe4 (tools/generate_doa_roster: refuse duplicate registry agent_ids; unwritable --out is a REFUSED line, S4-19)

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Claim: R-PR667-2afc0fe. Head fetched from refs/pull/667/head; one commit on main; 2 files (+111/-3): tools/generate_doa_roster.py and tools/tests/test_generate_doa_roster_input_guards.py. Author and committer: Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).

## Verdict: PASS (head 2afc0fe4), with LOW test gaps for a new PR. Standing: green CI on the landing head.

## Objections first (FORCE-O)
1. The assertion `"duplicate" in err` in `test_a_duplicate_agent_id_is_refused_naming_the_second_record` is vacuous. The registry path is printed in the REFUSED line and pytest's tmp_path directory is named after the test (`.../test_a_duplicate_agent_id_is_refused_.../agents.json`), so the word "duplicate" is in the output whatever the message says. Mutant D5 (message text without "duplicate") passes the file; I confirmed by deleting only that phrase and re-running (7 passed). The other half of the assertion (`record 2`) is real (D4 kills). LOW.
2. The temp file left behind after a failed write is not pinned. D9 (the whole `finally` cleanup removed) survives: in the directory case the tmp is a sibling of the directory (`adir.tmp` is not asserted on, only `adir`'s contents) and in the file-blocker case the tmp can never be created. Measured on the head: after refusing `--out` = a directory, the parent holds only agents.json, adir, manifests (no `.tmp`), so the code is right; the test just would not notice a regression. LOW.
3. The header docstring of the tool lists the REFUSALS (exit 2, nothing written) and was not extended with the two new ones (duplicate agent_id, unwritable --out). LOW doc gap.
4. D10 (an OSError while unlinking the tmp is no longer swallowed) and D11 (refusal wording) survive; the first needs a failing unlink to test, the second is cosmetic. LOW.
Steelman: a registry with two records for one agent silently produced a roster built from the later record's data; now it is refused naming the record index, and an unwritable `--out` ends as one REFUSED line with the exception class only (the OS message can quote a path), instead of a traceback. Case-distinct ids stay distinct (D3 killed), so no new equivalence is introduced.

## Runs (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1, absolute PYTHONPATH)
- new file: 7 passed. The tool's existing test file tools/tests/test_generate_doa_roster.py: 29 passed.

## Mutants (generate_doa_roster.py; kill = the PR's test file; baseline 7 passed)
| id | mutation | result |
|---|---|---|
| D1 | duplicate check removed | KILLED |
| D2 | `seen.add` removed | KILLED |
| D3 | ids compared case-insensitively | KILLED |
| D4 | reported index off by one | KILLED |
| D5 | message loses the word "duplicate" | SURVIVED (objection 1) |
| D6 | mkdir moved outside the try (the old placement) | KILLED |
| D7 | OSError not caught | KILLED |
| D8 | refusal echoes the OS error text | KILLED |
| D9 | tmp cleanup removed | SURVIVED (objection 2) |
| D10 | unlink OSError not swallowed | SURVIVED (objection 4) |
| D11 | refusal wording changed | SURVIVED (cosmetic) |
| D12 | duplicate check skipped for retired records | KILLED |
Total 12; 8 killed, 4 survivors (D5, D9, D10 real gaps; D11 cosmetic). Survivors were not run against the wider tools suite (the claimed file is the only one that touches these lines).
