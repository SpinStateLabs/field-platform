# Stage 3 readiness check (fp-estate-check, read-only, 2026-11-09 ~02:50Z)

No estate write was made. Fly read: one `fly ssh console` read-only health command (inline script, no file written). A first attempt to `sftp put` a probe failed on a missing app flag and wrote nothing. GB10: read-only commands only. The field-gate hook did not time out.

## 1. GB10 Stage 2 state (direct read, HIGH)
- Kill-switch `operator_mode` = enforce; the other seven (registry, delegation, governor, fedbroker, ledger, console, lifecycle) = log-only. Only the kill-switch container carries FIELD_OPERATOR_REQUIRE=1.
- `dropped_unauthenticated_records` = 0 and `dropped_refused_records` = 0 on all eight. Kill-switch `refused_count` = 45, unchanged since the 0430 read (still unexplained, LOW). All containers healthy. Kill-switch started 2026-11-07T00:08:42Z (matches the Stage 2 arm time).
- Canary: container up; `halted` flag not re-read this pass (no safe endpoint found in this check) - MEDIUM that it is not halted (all counters zero, containers healthy). The 0430 read said halted=False.
- Window monitor since the 01:13Z gap on Nov 7: I cannot confirm. The host has no monitor process and no stage-run script after s3-0 at 2026-11-07T08:32Z (host `~/.stage0-run`). No estate-deployer report on comms after 0430Z on Nov 7. The harness task b0v7tfunq lived in the estate-deployer session, not on the host. Conclusion: counters are zero NOW, but no evidence of continuous monitoring over roughly 46 h (LOW that none ran, HIGH that none is visible). Cumulative counters would still show any transient drop only as a non-zero value; they show none.

## 2. Build and go sentence
- Running build on all eight = 41afda50 (HIGH, /health build_sha and host checkout HEAD).
- origin/main = 7a42cb94 (HIGH). 41afda50 is an ancestor of main; main is 161 commits ahead. Not judged which of those are Stage 3 entry fixes (that was the architect's open question in the 0430 report).
- Go sentence per the 0430 report: `GO STAGE 3 41afda50` (MEDIUM). The format is not on main: `git grep "GO STAGE"` finds nothing outside tests. tools/stage_controller.py `preconditions` only requires a non-empty string, at most MAX_GO_SENTENCE, with no content problem (no 16-hex run). The controller does NOT verify the sha8 in the sentence; it keys alerts-proven and G21 records to the build sha8 (stage_controller.py lines 278-298).

## 3. GB10 renewal job (direct read, HIGH)
- Crontab: one renew_token line, and it passes `--operator-id job-renewal-gb10`. DONE since the 0430 report.
- `~/vt-renewal/renew_token.py` sha256 prefix ec09bc90843820ee = tools/renew_token.py at origin/main (same prefix, LF-normalised and raw) and at 41afda50. `SHA256SUMS` in that folder matches. Host files dated 2026-11-07 03:32 EST (08:32Z), after the 0430 report. Backups `crontab.before*` present.
- Not shown: a renewal actually run under the new identity. The last log line (Nov 8 14:35 EST) says "not due: 20 days left" (token expires 2026-11-29); its granted_by field names Don. So the new identity is configured but unexercised (MEDIUM).
- A `job-renewal-gb10.key` was not seen in `~/vt-renewal` by my `ls` (key files may live elsewhere; the 0430 report said key files present). Not verified (LOW).

## 4. Stage 3 preconditions changed since 0430
- B-S3-1: PR 837 MERGED 2026-11-07T18:25:26Z, merge 2bc5643e7, CI 14/14 (gh). CLEARED.
- P29: efe430bc6 is an ancestor of 41afda50 (git). MET.
- GB10 renewal job: fixed (section 3). MET, with the unexercised caveat.
- Controller records (alerts-proven, G21 for 41afda50): NOT FOUND. The records file default is `stage-controller-records.jsonl` in the working directory; I did not find it on the GB10 or in the local searches I could finish. I do not know (UNVERIFIED). Gate G22 was recorded per the 0430 report.
- Still open from 0430: live R-1 rehearsal (Don), s3-6 `--expect-mode` Stage-2-shape check (not edited; needs a dry run), Don's line 18 (CONFIRMED by Don per the 0500 answers).
- Stage 2 window judge ran only as the host-side record (armed 00:08:42Z, closed clean 01:14:13Z per the 0430 report). A new window record with the merged judge (PR 837) is not on the host: no stage1_window run since. UNVERIFIED whether Stage 3 needs it re-run.

## 5. Fly (direct read, HIGH unless tagged)
- App runs image main-3804d0b, one machine, version 19, started, 3/3 checks passing, last updated 2026-11-06T09:19Z. 3804d0b9 is an ancestor of main (211 commits behind).
- Every service reports build 3804d0b9. Eight operator-block services plus kill-switch: `operator_mode` log-only, `dropped_*` 0/0, kill-switch refused_count 11. That is the Stage 4a shape (LOG-ONLY armed). Not REQUIRE.
- 4a soak age versus the f4lib floor: floor value NOT FOUND (f4lib is under tasks/ in a private workspace, not on main or comms). Any secret set restarts the machine, so 4a was armed no later than the last update: age at most about 41 h at 2026-11-09T02:50Z (MEDIUM). Whether that clears the floor: I do not know.
- PR 867: still OPEN and DRAFT, head 37e59262, CI 7/7 SUCCESS (gh). Not merged. Comms: reviewer-9 filed "pass-with-conditions" on 37e5926 (stale runbook line 1486 and docs/ENVIRONMENT.md row 67 are conditions; I read items 1-5 of that report), and verifier-2 filed a full-16-suite report on it (GX10 16/16 result line not read: UNVERIFIED by me).
- Redeploy would need: 867 undrafted, conditions closed (runbook/ENVIRONMENT.md text), merged with CI green; then a Fly image build from main (scripts f4b/fly-deploy on rog-command, authorized by Don 2026-11-07 1525Z), then the internal-secret-hash set (authorized 1530Z, machine-to-machine only) and the G22-style check. Fly's 4b still needs E1 (GB10 Stage 3 record), E2 (renewal record), the soak floor, all internal callers carrying identity, red-team no-blocker on the armed build, rollback rehearsed. 4b cannot precede GB10 Stage 3.

## 6. What remains before Don can say the go sentence
Only Don can do:
1. Say `GO STAGE 3 41afda50` (or the new sha8 if the estate is redeployed first) when the coordinator asks (Don's 0500 answer 4).
2. Attend the live R-1 rehearsal with his key and break-glass (ruling moved it to Stage 3 entry).
3. (Fly later) type any Stage 4b go sentence f4lib requires.

A machine can do:
4. Record controller records for 41afda50: `record alerts-proven` and `record gate G21` (G22 was recorded). I found no records file and cannot verify these exist.
5. Exercise the renewal job once under job-renewal-gb10 (due in about 13 days) or dry-run it: proves the identity works. Not required by a stated gate.
6. Dry-run the proposed Stage-2-shape `--expect-mode` check in s3-6 rollback before Stage 3; estate-deployer asked "say go" for the dry run (0430 report).
7. Restart Stage 2 monitoring. Nothing visible has watched since the Nov 7 gap; Stage 2 has been armed about 46 h.
8. Re-run s3-0 for the exact current state; last host run was 2026-11-07T08:32Z.
9. Reconcile the kill-switch refused_count 45 (unexplained since 0430).
10. Close PR 867 conditions (docs), undraft, merge, then Fly redeploy and hash set.

Blocked / undecided:
11. Architect ruling: do any of the 161 main-only commits since 41afda50 count as Stage 3 entry fixes? If yes, a redeploy resets the GB10 to Stage 0 (about 3.5 h, two Don sentences, new sha8). The 0430 report recommended no redeploy; nothing since overturns that, but no one has ruled.
12. Fly 4b is blocked on GB10 Stage 3 (E1) and on the f4lib soak floor and E2 (unverified here).
13. Whether the merged window judge (PR 837) requires a fresh Stage 2 window record at Stage 3 entry: not established.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
