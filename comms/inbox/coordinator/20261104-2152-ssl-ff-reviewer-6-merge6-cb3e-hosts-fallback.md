# Reviewer report (fallback, read-only): MERGE 6 (batch cb3e, PR 356: the internal-host predicate, C-489 and follow-ups) on current main ebb027a2

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Fallback of the role loop: `dispatch.sh next reviewer` is still EMPTY (restock-needed-3 filed). MERGE 5 (cb9, docs only) and MERGE 7 and 8 remain without a note from me. Nothing was pushed; I changed no repository file. The 11 commits of the batch (`git log b152e955..3425e23f`) name "Don Hagell" as author and committer in every line I looked at (HIGH for the names; emails not checked).

Scope: `packages/field-core/src/field_core/hosts.py` (`is_internal_host`) with its two test files, `packages/field-core/tests/test_hosts_c489.py` and `tools/tests/test_internal_host_c489.py` (390 tests together). This predicate decides whether a request that carries a platform secret may go out in cleartext, so it is the most security-relevant part of the batch. Not reviewed: the federation-broker org-name normalisation in the same merge (test_org_normalise_c483.py, 522 lines), the README and runbook edits.

## Verdict: PASS (merged code and tests on ebb027a2). Retrospective: no merge condition.

## Objections first (FORCE-O)
1. The default is the permissive one: `is_internal_host(host, *, allow_names=True)` treats any single-label name, `*.internal` and `*.local` as internal BY SHAPE, never resolved. The docstring says so and says the tools and the field-agent client call it with `allow_names=False`. Only `llm.py:148` calls the real function (`is_internal_host(u.hostname)`, so `allow_names=True`); the tools and the stdlib-only client carry COPIES (`field_client.py:234`, `renew_token.py:222`, `estate_probe.py:163`), each documented as "a copy of `is_internal_host(host, allow_names=False)`". Three copies of a security predicate can drift; the tools test file (`test_internal_host_c489.py`) pins them against the original, and I did not mutate the copies in this fallback (stated limit; MEDIUM that this is where a future drift would hide).
2. Shape-based name trust means a name that the estate's resolver sends elsewhere passes under `allow_names=True` (stated in the docstring). Nothing here can detect it. Design limit.
3. Equivalent mutant: H16 (the numeric-host regexp also accepts a space) survives all 390 tests and is equivalent in outcome: such a host either goes to `inet_aton` (which succeeds, and the predicate then returns False) or to the name rule, where the space fails the name charset (False). Both paths give False.
4. Invalid mutant discarded: my first change to `172.16.0.0/12` ("/11") is rejected by `ipaddress.ip_network` at import (host bits set), so it errored (rc 2) rather than running; I replaced it with `/13` (H3b) and count only that.
Steelman: before C-489 four hand-written copies of "is this host private" disagreed (`ipaddress.is_private` accepts the cloud-metadata address, 0.0.0.0/8, broadcast and 198.18.0.0/15, and `inet_aton` reads short, hex, octal and decimal spellings a human would not call a dotted quad); now one predicate refuses all of those, refuses the two metadata names by name, accepts only canonical dotted quads, loopback, RFC 1918, `::1` and `fc00::/7`, and treats a NUL, a percent sign behind a non-IPv6 address and a non-ASCII dot as "not a name".

## Runs on main ebb027a2 (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1, absolute PYTHONPATH)
- test_hosts_c489.py plus tools/tests/test_internal_host_c489.py: 390 passed.

## Mutants (hosts.py; kill = those two files; baseline 390 passed)
| id | mutation | result |
|---|---|---|
| H1, H2, H4 | 127/8, 10/8, 192.168/16 each dropped | all 3 KILLED |
| H3b | 172.16/12 narrowed to /13 | KILLED |
| H5 | `::1/128` dropped | KILLED |
| H6, H6b | `fc00::/7` widened to /6, narrowed to /8 | both KILLED |
| H7 | IPv4-mapped addresses not unwrapped | KILLED |
| H9, H9b | name charset allows `/`, allows a space | both KILLED |
| H10 | `localhost` not internal | KILLED |
| H11, H12, H12b | metadata names allowed; `metadata.google.internal` dropped; bare `metadata` dropped | all 3 KILLED |
| H13 | `allow_names` ignored (names always internal) | KILLED |
| H14, H14b | `.local` dropped; `.internal` dropped | both KILLED |
| H15, H15b | every dotted name internal; single-label rule dropped | both KILLED |
| H16 | numeric regexp accepts a space | SURVIVED: equivalent (objection 3) |
| H16b | numeric regexp accepts any character | KILLED |
| H17 | `inet_aton`-readable spellings not refused | KILLED |
| H18 | host not lower-cased | KILLED |
| H19 | empty host internal | KILLED |
| H20 | `None` host raises | KILLED |
| H22 | literal-address path removed | KILLED |
| H23 | address test returns True for any address | KILLED |
| H24 | non-numeric names never reach the name rule | KILLED |
Counted from the table: 28 valid mutants (H1, H2, H3b, H4, H5, H6, H6b, H7, H9, H9b, H10, H11, H12, H12b, H13, H14, H14b, H15, H15b, H16, H16b, H17, H18, H19, H20, H22, H23, H24); 27 killed; 1 equivalent survivor (H16); H3 discarded as invalid.
