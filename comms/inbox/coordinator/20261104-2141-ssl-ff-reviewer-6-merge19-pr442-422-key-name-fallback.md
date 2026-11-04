# Reviewer report (fallback, read-only): MERGE 19 (PR 442, C-1128: 422 key-name echo guard in agent-registry and federation-broker) on current main ebb027a2

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Fallback of the role loop after `dispatch.sh next reviewer` answered EMPTY again (restock-needed-3 is filed; `dispatch.sh level` shows `reviewer unclaimed=0 RESTOCK`). MERGE 14 was reviewed in the previous fallback report (merge14-environment-anchors-fallback). Why MERGE 19: MERGE 10 has the Lane N post-merge note and MERGE 1 has the BATCH-cb2 done entry; MERGE 19 is covered only by the Lane A audit table ("OK") and has code. Nothing was pushed; I changed no repository file.

Scope: the three commits of PR 442 as merged (6385f877: 0cd99e67 tests, 2349eeb5 code, merge of b39287c1), read on main today: agent-registry `api.py` (own handler removed, `install_validation_handler(app)`), federation-broker `api.py` (own handler kept, `loc` names replaced), tools/tests/test_422_handler_installed_c1114.py (the guard now looks for a Call node). Author and committer of all three: Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH, from `git log`).

## Verdict: PASS (merged code and its tests on ebb027a2). No merge condition (retrospective).

## Objections first (FORCE-O)
1. Two services still use different 422 code paths on purpose: federation-broker keeps its own handler because the helper would replace its validators' explanatory messages (NOT_YET text, "F3, Don's decision"). The new code there redacts only `loc` (a string that is not a declared name), and keeps `msg`. A caller-chosen text can still reach the response through `msg` if a federation validator quotes its input; I did not enumerate the validators (not verified; LOW to MEDIUM, and it is the ruling the code names).
2. The new federation-broker test file proves the marker is absent, not that declared field names survive: mutants B2 (every string name redacted) and B6 (the known-name set empty) pass `test_422_key_name_c1128.py` (3 passed) and are killed only by other tests in the whole federation-broker suite (12 failed each, measured). So the pair of properties "caller names gone, declared names kept" is pinned by two different files; if the second were removed the first alone would accept a handler that redacts everything. LOW.
3. The call-detection guard in tools/tests/test_422_handler_installed_c1114.py has two copies of the `Name or Attribute` condition (lines 27 and 199 on main). Line 199 comes from a later commit that is not part of this merge; I mutated only the copy this merge introduced (line 27) and did not review the second clause. Stated limit, not a finding.
4. Static guard, as its own docstring says: it reads source text for a Call node; it does not send a request. Per-service request tests exist only for the services in `MEASURED` (agent-registry joined that set in this merge; I re-ran its two new tests: 5 passed).
Steelman: before C-1128 agent-registry's own handler passed a body key through `loc` unless it looked like a secret, and federation-broker's returned `loc` untouched, so a made-up key came back on `/agents`, `/discover` and `/crossing`. Now the field-core helper (agent-registry) and an explicit `loc` redaction (federation-broker) replace any name that is not declared; the guard is an `ast` Call scan, so a comment, a string, an import or a bare name no longer counts as "installed".

## Runs on main ebb027a2 (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1, absolute PYTHONPATH)
- agent-registry test_422_key_name_c1128.py: 5 passed. federation-broker test_422_key_name_c1128.py: 3 passed. tools/tests/test_422_handler_installed_c1114.py: 38 passed. Whole services/federation-broker/tests: 191 passed.

## Mutants (kill = the merge's own test file; baselines 3, 5 and 38 passed)
| id | mutation | result |
|---|---|---|
| B1 | federation-broker `loc` redaction removed | KILLED |
| B2 | every string name redacted (declared names too) | SURVIVED target; KILLED by the whole federation-broker suite (12 failed) |
| B3 | no name redacted | KILLED |
| B4 | the replacement text is the name itself | KILLED |
| B5 | the `input` key kept in each error | KILLED |
| B6 | known-name set empty | SURVIVED target; KILLED by the whole suite (12 failed) |
| B7 | status 400 instead of 422 | KILLED |
| B8 | agent-registry `install_validation_handler(app)` removed | KILLED |
| H1 | guard no longer recognises an attribute call (`m.install_...(app)`) | KILLED (1 failed) |
| H2 | guard no longer recognises a bare-name call | KILLED (13 failed) |
| H3 | any Name node counts as an install | KILLED |
| H4 | text scan instead of an `ast` scan | KILLED |
| H5 | federation-broker dropped from NOT_YET | KILLED |
Total 13 counted from the table: 11 killed by the merge's own tests, 2 (B2, B6) killed only by the whole suite, 0 surviving everything, no equivalent mutants identified.
