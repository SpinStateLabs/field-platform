VERDICT: PASS WITH CONDITIONS on 2e00c73ed070005383d723888e86c349365d7d36 (UNVERIFIED: cloud reviewer, docs read against source at that head; no suite run, CI not read)

Head matches the card. Two commits on main 5808a5c (9192e30, 2e00c73); author and committer of both are the no-reply identity. One file: docs/adr/ADR_Pack_07_Compliance_Crosswalk.md, +6 (the second commit edits the same note, 2 lines).

OBJECTIONS FIRST
1. The note's counts (13 controls, 52 entries, 16/23/13) are a snapshot inside an ADR; they go stale on the next matrix edit. The note does carry a recount command, which mitigates this, but a count in an ADR is still a claim with a shelf life.
2. "Suggestions ... never write a pack" is cited to suggestions.py:15-19, which states that suggestions never touch CONTROLS and never mint citations (lines 16-18). It does not literally say "never writes a pack"; that is an inference from the module boundary.
3. "A model is used only by the optional suggester": the package has other files that mention a model-API or HTTP client (cli.py, api.py, mapping.py; regwatch.py fetches pages with an HTTP client). I read suggestions.py and evidence_pack.py, not every call path in cli.py/api.py. If one of them calls a model outside the suggester, the sentence is too strong.
4. Note 3 and note 1(c) are absence claims ("no golden set", "no tenant concept"). Both hold on a search today; they say nothing about branches or other repositories.
5. "Verified" status: the 16 cited entries each carry a reference, a source_url and a retrieved date, but the PR cannot show that the cited page supports the mapped control text; only a human with the source can.

ASSUMPTIONS
A1 Source of truth is the repository at the PR head. A2 "main branch" in the note = 5808a5c (merge base). A3 No network fetch of any cited regulation page.

REASONING
1. Counts: I loaded mapping.py from the PR head with the library alone and counted: 13 controls, 52 citation entries, statuses cited 16, pending-text 23, pending-purchase 13. Matches the note exactly (HIGH).
2. For each of the 16 cited entries I checked the fields reference, source_url and retrieved are non-empty; only the free-text note is empty on 12 of them (by design, not claimed by the note). No cited entry lacks a source field (HIGH). Whether the source supports it: not verified.
3. Note 1(a): generate_pack at evidence_pack.py:142; the module header (lines 1-4) says it assembles declared and evidenced items; imports (lines 30-37) are engine, mapping and standard library, no model client. The ADR it contradicts says the LLM "drafts evidence-pack prose" (ADR lines 12, 27, 83): correctly flagged. suggestions.py:8-18 shows the suggester is off by default and never touches CONTROLS. HIGH.
4. Note 1(b): RETRIEVED at mapping.py:31 (value is a date string) and INGESTION_LOG at mapping.py:51 confirmed; regwatch.py hashes page text (regwatch.py:232, 308) and flags frameworks stale (regwatch.py:6). The ADR's retrieval/re-index claim is at ADR lines 48-50. A search for "embedding", "vector", "re-index" finds no code. HIGH.
5. Note 1(c): a case-insensitive search of service source and tests for "tenant" returns nothing; the ADR claim is at ADR line 51. HIGH.
6. Note 3: the only "golden-set" text in source is suggestions.py:21-22 (the cited 21-23 includes the closing quote line); the only "override" hits are the stale-block comment at evidence_pack.py:15 (and :46, :63, api.py:170, all "no override"), a unicode-override docstring, and a model-id environment override (suggestions.py:35): none is a reviewer-override log. HIGH. The ADR says reviewer overrides are logged as the drift signal (ADR line 42): correctly flagged.
7. Note 4: self_manifest.yaml:21 principal and :52 granted_by read "Founder & CTO, Spin State Labs"; the comment about a client CCO is at lines 2-3 (the note says :2). HIGH.
8. Diff scan (both commits): no estate address, flag value, build SHA, deploy status or credential; only variable-free file and line citations. HIGH.
9. Process lapse, disclosed: in a scratch worktree my import ran with the isolated-mode flag, which ignores the bytecode-off variable, so a pycache directory was written there. The worktree was deleted; nothing was committed.

CONCLUSION
PASS WITH CONDITIONS. The note's claims match source at the cited places and the figures reproduce. Conditions, none blocking:
- C1 F-C654-1 reword the "never writes a pack" cite to what the lines say.
- C2 F-C654-2 before relying on "a model is used only by the suggester", read the call paths in cli.py and api.py (I did not).
- C3 F-C654-3 consider dating the counts ("on 5808a5c") in the note.

FINDINGS
F-C654-1 LOW, docs/adr/ADR_Pack_07_Compliance_Crosswalk.md note 1(a) (suggestions.py:15-19 cited; says CONTROLS and citations, not the pack). HIGH.
F-C654-2 LOW, same note, "only by the optional suggester" unverified for cli.py and api.py. MEDIUM.
F-C654-3 LOW, note 2 counts undated. HIGH.
F-C654-4 INFO, citation :2 for the CCO comment is :2-3. HIGH.

NOT VERIFIED: that each cited source supports its control text; cli.py/api.py model calls; CI; the service test suite (not run).
