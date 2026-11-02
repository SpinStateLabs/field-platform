# reviewer Lane 15: C-1166 (WP11, read-only), enforcement gate and ADR-0071 / ADR-0072 lockstep status

Read at: field-platform main 40aec372 (git ls-remote), SpinStateLabs/Force-Field main c40b9b02 (2026-10-25, gh api). Read-only: nothing pushed to either repository, nothing edited, no estate value read. Counts, names and shas only. The live hook run is Don's and is not attempted here.

## OBJECTIONS FIRST (limits)
1. "Draft or stale" is read from PR state and branch compare on 2026-11-03; the Force-Field ADR texts are not in this repo, so I do not check what the ADRs decide.
2. `ahead_by` on a squash-merged branch counts the pre-squash commits, so a non-zero value does not mean unmerged work; I report it, I did not diff those commits.
3. The "what is owed" part for the live proof rests on my own project notes (2026-09-12, 51 days old) and the Force-Field CHANGELOG; I do not know whether Don has done a live run since. Not in source.

## Force-Field PRs (gh pr list, all states): 17 PRs, 16 MERGED, 1 OPEN
- ADR-0071 (opt-in policy verdicts, field 1.3.0): PR 10 MERGED 2026-10-21 (head 326c05d1). Branch `claude/adr-0071-gate-policy-verdicts` still exists, tip af3392f4, diverged from main: ahead 2, behind 8. The tip is not the merged PR head (326c05d1), so the branch carries 1 or more commits after the merge: I do NOT know what they are. MEDIUM-LOW (stale branch with unexplained tip): delete it or say what af3392f4 holds.
- ADR-0072 (estate kill through a local sentinel): PR 11 MERGED 2026-10-21 (head 2d67e991 = branch tip). Branch still exists, ahead 5, behind 7 (squash). Stale, harmless.
- ADR-0075 (post-tool evidence hook, field 1.5.0, and the ask-is-not-approval note): PRs 12 and 13 MERGED 2026-10-22, tips equal the PR heads.
- Gate work since: PR 14 (symlinks and junctions on Windows, windows-latest CI), PR 15 (cmd / PowerShell / link-glob fixes), PR 16 (per-call ledger cost O(new events)), PR 17 (a gate hook that fails or times out blocks): all MERGED 2026-10-24..25.
- The one OPEN PR: 8, DRAFT, `claude/upbeat-carson-2wqhg5` (docs: local-session handoff), last updated 2026-10-21, ahead 1, behind 11 against main c40b9b02: STALE, 13 days old.

## field-platform side of the lockstep
- The two field-platform lockstep branches named in the C-61 triage (`claude/adr-0071-field-core-lockstep`, `claude/adr-0072-estate-kill-watcher-r2`) were squash-merged as #9 and #12 and no `claude/adr-*` branch is on origin (ls-remote); the C-49 note (Lane 5) says the same. HIGH.
- Schema lockstep MEASURED on current main: the manifest schema in Force-Field (`plugins/field/skills/field/manifest-schema.json`) and both vendored copies in field-platform (`packages/field-core/src/field_core/schema/manifest-schema.json`, `plugins/field-agent/templates/manifest-schema.json`) have the same md5 after line-ending normalisation (8acbe8cb): in lockstep. The sizes differ only by line endings (16251 B against 16547 B). HIGH.
- Plugin versions are NOT a lockstep pair: Force-Field `plugins/field` is 1.5.1; field-platform `plugins/field-agent` is 0.1.6, a different plugin. I draw no drift conclusion from them.

## What is owed for the live proof
- Force-Field CHANGELOG [Unreleased] holds 3 gate fixes marked "not yet released, no version bump" (PR 14 and 15 Windows link handling, PR 16 ledger cost) plus a "Known limitations" list still open on Windows (dash-named links, `%COMSPEC% /c` and `winpty cmd /c` forms, brace expansion, a link made in the same command). MEDIUM: a release (version bump and CHANGELOG move) is owed before a live proof can name a version. Whether PR 17 is in that section: not checked.
- The CHANGELOG records CI on `windows-latest` under Git Bash and a Windows launcher-suite re-run (25/25), both model-free. It records no live `claude -p --plugin-dir` run on Windows (searched for "live" and "claude -p": no such entry). Owed, and Don's: one recorded live run on Windows. Until then the supportable claim is "verified model-free under Git Bash and in CI", as my 2026-09-12 note says.
- Not done and not mine: the live run; the release; the stale draft and branches above.

## ASK
Coordinator or Don: (1) decide the fate of draft PR 8 (close or refresh); (2) have the Force-Field owner say what af3392f4 holds or delete `claude/adr-0071-gate-policy-verdicts`; (3) schedule the release of the 3 unreleased gate fixes ahead of the live run. I do not touch Force-Field (protocol).
