VERDICT: PASS WITH CONDITIONS on d7f1058771b755ac3a3a56ba14bcec60459cb151 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the doc-pin tests ran: 8 passed in the runbook pin file, the earlier host and environment-doc files 316 passed)

Delta review of PR 356 from 846242e (my C-696 head; the C-689 reviewer reported two FAILs on three doc-pin tests) to d7f1058. Head matches the card. One commit on top; author and committer are the no-reply Don Hagell identity.

OBJECTIONS FIRST
1. Did the predicate change? NO. The delta touches only docs/ENVIRONMENT.md (4 lines) and docs/runbooks/token-renewal.md (4 lines); no file under packages/, tools/ or services/ changed (git diff 846242e..d7f1058 lists two docs files). So every finding of my C-696 report about the predicate stands unchanged. HIGH.
2. Forms still missed, re-probed on this head (names on): an ideographic-dot spelling of a public address is still accepted by cleartext_ok (True; httpx connects to the public address, see C-696); metadata.google.internal still accepted (True); a raw bracketed public IPv6 string still accepted by the predicate (True, not reachable through the URL parser). Correctly handled: IPv4-mapped public IPv6 refused, a zone-id link-local refused, octal and hex spellings of loopback accepted as internal, a decimal spelling of a public address refused. MEDIUM (finding F-C696-1 open).
3. The doc-pin fix: the runbook pin now equals the file's hash (the sha256 prefix 3b51e89f98db is both the hash of tools/renew_token.py at this head and the value in the runbook, 4 occurrences); the runbook pin test passes (8 passed). The earlier value was the hash from before the predicate commit changed renew_token.py, which is why the pin failed. The pin is a content hash of a public file, not an estate SHA. HIGH.
4. The ENVIRONMENT.md line cells for llm.py moved with the code (the doc test that pins line references passes in the 316). A line-number cell is fragile by construction: any edit to llm.py again breaks it. LOW.
5. Two-FAILs-on-three-tests claim: I could not see the C-689 run; the three tests I ran that name the hash pin and the env doc are green now. NOT VERIFIED that these are exactly the three.

ASSUMPTIONS
A1 "Doc-pin tests" = the runbook pin test (tools/tests/test_runbook_pins_c465.py) and the environment-doc test (tools/tests/test_environment_doc.py). A2 Probes call the predicate and cleartext_ok directly.

REASONING
1. Diff since 846242e: two docs files only. HIGH.
2. Pin value: sha256 of tools/renew_token.py at this head begins 3b51e89f98db; the runbook carries it 4 times; the pin test passes. HIGH.
3. Probes: as in objection 2. HIGH.
4. Diff scan of the delta: no estate address, flag value, deploy status or credential; one content hash of a repository file. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The doc pins are green and the predicate is unchanged, so the C-696 conditions (C1 non-ASCII dots in names, C2 metadata names, C3 single-label strictness, C4 the gateway's remaining is_private) remain open.

FINDINGS
F-C761-1 MEDIUM, packages/field-core/src/field_core/hosts.py:28-30 (name rule) with llm.py:148: same as F-C696-1, unchanged. PROVEN.
F-C761-2 LOW, docs/ENVIRONMENT.md and docs/runbooks/token-renewal.md (a hash and line cells that break on the next edit). HIGH.

NOT VERIFIED: the C-689 failing-test list; CI; the full tools suite on this head.
