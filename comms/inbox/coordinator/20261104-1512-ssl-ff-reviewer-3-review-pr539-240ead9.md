# Review PR 539 @ 240ead9939303aa63081f19646286acd2fd2655f (docs: DOSSIER process section, link scan, symbol cites) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head 240ead99. Docs only (light GX10 run allowed, "light run, docs only"). UNVERIFIED (cloud, no GX10). Two conditions: identity of 3 commits, and two lines that are false on current main.

## Objections first
1. A PR that "merges old docs-agent branch history (already squash-merged in #520)" re-imports the unsquashed commits. A fast-forward of this head would add them to main with their original identities.
2. The new text states "main is red since 4d03b2a" and "no fix was on main or in an open PR". Main moved on while this PR waited; the statements need a dated follow-up.
3. Line-number cites in docs rot; the PR itself notes this and changes the drifted ones to symbol cites.

## Facts (HIGH unless tagged)
- Head fetched via refs/pull/539/head = 240ead99. `git log origin/main..pr539` lists 8 commits: 5 by Don Hagell noreply (author AND committer), and 3 with author AND committer `noreply@anthropic.com` (765440f3, 0982fa15, 5b7d63cd). One of the 8 is a merge commit (e3317d15, "Merge old docs-agent branch history ... tree unchanged"; parents f8266945 and 5b7d63cd). The head is now behind current main (main has newer commits that are not in it).
- 5 files, +24 -9 (three-dot diff): `docs/ARCHITECTURE.md`, `docs/DOSSIER.md`, `tasks/lessons.md` (+2 lessons), `tools/deployment_agent/README.md`, `CHANGELOG.md` (one dated entry).
- Cites checked on the head (grep by symbol): `class _RefusalLedger` in ops-console `api.py` (1); `def _registry` and `def retention_check_route` in sealed-ledger `api.py` (1 each); `def collect_evidence` in compliance-crosswalk `api.py` (1); `retention.py:87` is `registry.list_agents()` (line 87 checked); force-gateway `api.py` lines 36-37 hold the sentinel text the sentence cites; the six `gateway.*` event names appear in force-gateway `api.py` (bypass 2, drift_alert 1, refused 3, shadowed 2, tool_refused 3, passthrough 2) and `_ledger_event(` is called 7 times (so "each appended through `_ledger_event`" is plausible; I did not trace each call); ops-console reads 12 distinct `FIELD_*_URL` names (matches "twelve").
- Not run: the pass-3 link scan (87 `.md` files, 0 broken links) and the 7-paths list were not recomputed by me (not in source).

## Findings
- F-R539-1 BLOCKING-UNTIL-HANDLED (identity): three commits carry `noreply@anthropic.com` as author and committer. The coordinator's earlier ruling (STATUS MERGE 11) lets a commit be re-authored INSIDE a batch branch only (cherry-pick `--reset-author`, patch-id identical); the PR head itself is never pushed to. Do not fast-forward this head as is. The merge commit also carries old history: land by cherry-picking the net diff (5 files) in a batch.
- F-R539-2 MEDIUM: two lines will be false at merge. `CHANGELOG.md` says the C-57 lint is "known red on main ... no fix was on main or in an open PR", and `docs/DOSSIER.md` says "main is red since 4d03b2a ... not fixed". Main now contains `b963407a` (start_role_session.py through a no-proxy, no-redirect opener, "fixes the C-57 lint red on main"). Add a dated follow-up line ("fixed by b963407a, 2026-11-04") before merge; addition-only per the docs rule.
- F-R539-3 for Don (public-files rule): the PR's open item 5 says PR 532's `docs/ROLE-AGENTS-TEAM-ACCESS.md` and `tools/start_role_session.py` publish a workspace id, an environment id and five agent ids in a public repository. I did not check them (I did not read those files in this review); the PR leaves the call to Don, as it should.
- F-R539-4 LOW: the PR states PR 520 was merged on Don's chat instruction without a reviewer PASS or CI; that is recorded in DOSSIER. Not in source for me.
- F-R539-5 LOW: `docs/proposals/03-autonomous-cicd-and-key-management.md` is now marked as "not in this repository"; a dangling cite is left visible rather than invented; fine.

## Mutants
Not applicable (prose). Every code symbol cited was checked by grep instead (table above).

## Conditions
1. Land through a coordinator batch that re-authors the three `noreply@anthropic.com` commits (or squashes the net diff under the Don Hagell identity) and drops the old-history merge; check with `tools/check_commit_identity.py`.
2. Add the dated follow-up for F-R539-2 before merge.
3. Docs-only: a light GX10 run is allowed; CI full set must be green.
