# R-16 reviewer report: compliance-crosswalk statements that read as compliance claims (main 444e49b)

VERDICT: the code and the stated figures (13 controls, 16 of 52 entries cited) are consistent and use no compliance-assertion wording; one README sentence claims a citation the table does not contain, and one guarantee row overstates what the guard test proves.

OBJECTIONS FIRST
1. I cannot verify that the 16 cited passages say what the table claims they say: that needs the three source texts read against the references; I did not do it.
2. A keyword scan misses a claim worded without the words I searched for.
3. The README is prose; a contradiction between prose and table is only findable by recomputing the table, which I did for counts and one control.

ASSUMPTIONS
1. Main 444e49b; `services/compliance-crosswalk` README.md, SPEC.md, src (mapping.py 335 lines, evidence_pack.py, api.py). [HIGH]

REASONING
1. Figures recomputed from `CONTROLS` (mapping.py): 13 controls, 4 frameworks, 52 entries: 16 cited, 23 pending-text, 13 pending-purchase. Per framework: osfi-e23 5 cited / 8 pending-text; eu-ai-act 5 / 8; nist-ai-rmf 6 / 7; iso-42001 0 cited / 13 pending-purchase. README.md:273, SPEC.md:15-17 and api.py:104 say "16/52" and "13 controls": all match. STATE.md:89 ("16/40 -> 16/52, same cited count; 12 new pending entries") matches. [HIGH]
2. Every cited entry carries reference + source_url + retrieved (0 violations over 16); no citation note and no control statement contains "complian", "certif" or "guarantee". The only occurrences of those words in src are the disclaimer, the word-discipline docstring (evidence_pack.py:4, :16) and regwatch.py:132 ("satisfy", about string matching). [HIGH]
3. MEDIUM-LOW, F-R16-1: README.md LIMITS (lines ~283-286): "Only FC-E-04 cites anything (EU AI Act Art. 14 para 1, partial, the passage FC-E-03 uses); the rest is pending." On main, FC-E-04's eu-ai-act entry is `pending-text`; the only EU Art. 14 citation is FC-E-03's. The sentence describes a citation that is not in the table (it matches the content of the unmerged branch `claude/adr-0074-crosswalk-gate-controls`, whose diff I saw earlier, PR 10: 17/52). It over-states the mapping, which is the failure lessons.md rule 4 names. Fix: either merge the mapping change or correct the sentence to "none of FC-E-04..06 cites anything yet". [HIGH on the mismatch]
4. LOW, F-R16-2: README "Enforced vs Declared": "No fabricated regulation citations can ship | Enforced in code | adversarial guard test on the mapping table". The guard (`test_adversarial_no_ungrounded_citations`) enforces form (reference, source_url, retrieved present); it cannot enforce that the passage exists or says what the note says. The row below ("The mapping table is *correct* against each framework | Declared only") is the honest half; the first row reads stronger than the test. Reword to "cannot ship without a reference, source URL and retrieval date". [HIGH]
5. Not verified: that each cited reference exists in the named source and supports its note (16 entries); that the AI Act Explorer mirror matches EUR-Lex (the README itself says to cross-check before external publication). I do not know. [HIGH on "not done"]
6. Sound: DISCLAIMER ("this system never asserts compliance; a named human signs, or nothing ships"), the pack refuses a blank signer and a stale corpus, ISO 42001 is entirely pending-purchase, and the README LIMITS open with "It cannot say you comply with X". [HIGH]

CONCLUSION
Fix the FC-E-04 sentence (or land the mapping), reword the guard-test row; have a human reader check the 16 cited passages against the sources before any external use. No compliance assertion found.
