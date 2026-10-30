# Groomer (Lane 9) to coordinator: GX10 HANDBACK. Everything below needs a GX10 run, a tool I do not have here, or an owner action. I keep the cloud reads; I stop at the line.

WHY: every review and scan I wrote is a cloud read (source reading, grep, a scratch interpreter, my own mutants). None ran the 16-suite set, CI, docker, caddy, a deployed estate or a history-scan tool. The coordinator's merge rule needs the exact head, a green GX10 run and CI; the items are listed by head so you can queue them. No estate value appears in this note.

A. PR HEADS I REVIEWED OR TRACKED, LATEST HEAD, GX10 16-SUITE RUN AND CI NEEDED (verdicts exist under the card shown; "PASS" is cloud-only until your run)
- PR 316 @6ae698f (C-456/C-544 console CSP; my C-515 PASS WITH CONDITIONS on 9b1fb08, delta C-567 open): ALSO needs `caddy validate` on integration/demo/Caddyfile and integration/fly/Caddyfile and one `curl -sI` of the console page and the stream route (does Cache-Control no-store beat the upstream's no-cache: F-C515-1).
- PR 317 @9cc5221 (C-138/C-555 half-up rate; C-543 PASS, C-588 PASS on 6f0afdd, delta C-614 open).
- PR 318 @33a8dc7 (C-476/C-486/C-494/C-547/C-557, the lifecycle client constructor; C-569 PASS WITH CONDITION, bypass C-592). Range of three commits.
- PR 319 @34895a4 (C-101/C-556/C-579 CI external-reference guard; edits ci.yml; delta C-593 open): needs `fly-image-smoke` SUCCESS on this head and the strict-YAML read.
- PR 321 @ddbeb71 (C-501 flaky-test naming; C-566 PASS, my C-594 yes): run the whole tools suite twice (the flake itself is not fixed).
- PR 322 @f6a9bbe (C-483 federation org normaliser; C-565, C-578 PASS; my C-595: merge this, close PR 327): needs the real two-process race on the GX10 and the whole federation-broker suite.
- PR 324 @ca70eec (C-502; C-572 PASS, my C-596: correct, but see C-623 for the sentinel URL echo).
- PR 325 @34e7554 (C-469 dead code; C-580 open).
- PR 326 @203810f (C-503 upstream-error helper; production, field-core/field-agent/sentinel; C-584 open).
- PR 328 @7679259 (C-512 resolved-model compose check; needs a real `docker compose config` output, which no cloud session has: C-585 open) and PR 329 @621d5d3 (C-500/C-506 compose key allowlist; C-589 PASS WITH CONDITIONS twice; conditions C-617): they edit the same file; one merges first.
- PR 330 @f09efe7 (C-511 slice 1 guarded operator pair; production across clients; C-586 open, HIGH CARE).
- PR 332 @4c12c15 (C-558 crosswalk wording; C-587 PASS on f9f90f7; delta in C-614).
- PR 336 @96d812e (C-574 kill-switch self-guard; three versions exist: also branches fix/kill-switch-self-guard-c574 and ...-c574-alt; C-610 read, C-618 open).
- PR 339 @097814d (C-548 innerHTML audit hardening, node plus acorn from npm: needs node and the network, which this container lacks for the acorn fetch check: C-620 open).
- PR 342 @4ea4db6 (C-560 public-safety paths, 24 files: C-619 open): after merge, re-run the C-540 scan classes on main.
- Docs PRs, light GX10 run (tools tests touching docs): 334 @8bea8c4 (C-545), 335 @9192e30 (C-549), 337 @99888f8 (C-559), 338 @8cc7e41 (C-571, also a comment line in tools/topology_lint.py: run topology_lint tests), 340 @1643d20 (C-577), 341 @cde3303 (C-550, comment-only code changes in force-gateway: run its suite). Also PR 290 @33b2c02 (soak times) and PR 297 @3bb2510 (lessons; its CI was red once on the flake) and PR 308 @7e0deec (Phase E).
- Merged, no action: batch BW (PRs 311, 309, 314 first commit) is on main 5808a5c per STATUS.

B. THINGS ONLY A GX10 OR A TOOL CAN CHECK (from my reports)
1. C-515 F-C515-1/-3: caddy validate and the header-precedence curl (above).
2. C-562 F-C562-4: a real history scan (gitleaks or trufflehog) over every ref including `refs/pull/*`, deleted branches, release assets: I could only scan `refs/heads/*` by shape (no credential found). Owner-run, on a trusted machine.
3. C-532: the deploy runbook's steps were never run by me; its behaviour and ordering are C-196's read (2026-10-31) plus presence checks. An estate dry-run is the owner's, never a cloud lane's.
4. C-533/F-C533-1: whether any estate-side script calls the alert library (only a host can say).
5. C-536/C-537/C-538: the demo numbers (event count, timings) need `bash integration/demo/run_demo.sh` on the GX10: record the real event count and drill timings for C-590.
6. C-529/C-530/C-531: runtime behaviour of the sentinel, crosswalk and gateway was read, not run.
7. C-218 (coordinator card): gx10_verify.sh still lacks `verify_sync`.
8. The whole-suite test count the docs now cite (8,308 collected) should be re-collected on the merged main when batch BW's successors land (C-499 recomputed it once).

C. OWNER ACTIONS (not a lane's, listed so they are not lost)
- Delete the mistaken remote branch test/console-innerhtml-audit-hardening-c548 (Lane 1's note; head 958260f, no PR, wrong committer identity).
- Close duplicate PRs: 313 (done), 315, 323, 327; and two of the three C-574 versions.
- Rulings: C-552, C-561, C-563, C-606, C-467, the F-C525-2 guard rule, the Cf normalisation (C-583 for the rest).

I will keep doing cloud-only work (reads, scans, grooming) and will not start anything that needs the items above. Poll interval stays 10 minutes while cloud cards remain (C-597 to C-605 and C-608 to C-612 are cloud reads) and 5 minutes when none do.
