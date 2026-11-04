# LANE O review: PR 591 (federation-broker home_org) @ cd9b1163

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head cd9b1163, tests only, 1 commit, Don Hagell numeric noreply, 1 behind origin/main 97dcfec1.

Objections first: (1) three survivors are `.strip()` on the home org value; the tests never set a padded FIELD_ORG_NAME, so padding is unpinned. (2) The non-list `peers` guard in `_lists_org` is unpinned. (3) Pins describe current behaviour; if blank-name handling changes in code, tests must change with it.

Baseline (unmutated): new file 26 passed; federation-broker suite 217 passed.

| Behaviour | Mutants | Killed (file) | Killed (older tests only) | Survived | Invalid |
|---|---|---|---|---|---|
| B1 home_org unset=default, set=as read | 6 | 5 | 0 | 1 | 0 |
| B2 blank home org matches no peer | 6 | 4 | 1 | 1 | 0 |
| B3 /health reports home org | 4 | 2 | 0 | 1 | 1 |
| B4 blank org blocks inbound at F.peer, org in context | 4 | 4 | 0 | 0 | 0 |
| B5 outbound attributed `<home org>/<agent>` | 4 | 3 | 0 | 1 | 0 |
| Total | 24 | 18 | 1 | 4 | 1 |

Totals counted from the table: 24 = 18+1+4+1.

Survivors (all real pin gaps, none equivalent):
- B1, B3, B5: `.strip()` applied to home_org() output (engine home_org, /health, outbound agent_id). A padded FIELD_ORG_NAME is not pinned.
- B2: removing the `isinstance(peers, list)` guard in `_lists_org`; a non-list peers value is not pinned.
Invalid (1): B3 variant did not compile to a distinct behaviour; excluded.

Conditions: add a padded-name test across home_org, /health and outbound attribution; add a non-list `peers` test. Confidence: HIGH on counts (harness run), MEDIUM on gap classification. Token/cost: I do not know.
