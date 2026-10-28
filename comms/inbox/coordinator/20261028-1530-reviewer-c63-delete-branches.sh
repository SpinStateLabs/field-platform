#!/usr/bin/env bash
# C-63 (was C-50): delete-list for remote branches of SpinStateLabs/field-platform.
# AUTHOR: teammate-don-reviewer, 2026-10-28. NOT RUN by the author. For DON'S APPROVAL; the coordinator runs it, never the reviewer.
# Safety: dry-run by default (prints what it would do). Execute with: DRY=0 bash delete-branches.sh
# Each branch is deleted only if its remote tip STILL equals the sha recorded below (the sha the evidence was taken at);
# a moved branch is skipped and reported. Never deletes main, comms, or the live branches listed in PROTECTED.
# Excluded on purpose (live): feat/machine-verifier-identity (#55), feat/alerts-ntfy (#56), feat/kr-r4a-rotator-core (#57), fix/renew-token-signed.
# Recovery: a deleted branch tip stays reachable on GitHub for the squash-merged PRs (refs/pull/<n>/head) and is restorable with
#   git push origin <sha>:refs/heads/<branch>   (shas below).
set -euo pipefail
REMOTE="${REMOTE:-origin}"; DRY="${DRY:-1}"
PROTECTED="main comms feat/machine-verifier-identity feat/alerts-ntfy feat/kr-r4a-rotator-core fix/renew-token-signed"
deleted=0; skipped=0
del() {  # del <branch> <recorded-tip-sha>
  local b="$1" want="$2"
  for p in $PROTECTED; do [ "$b" = "$p" ] && { echo "REFUSE protected: $b"; return 1; }; done
  local got; got="$(git ls-remote --heads "$REMOTE" "refs/heads/$b" | cut -f1)"
  if [ -z "$got" ]; then echo "ABSENT  $b (already deleted)"; skipped=$((skipped+1)); return 0; fi
  if [ "$got" != "$want" ]; then echo "MOVED   $b tip is $got, recorded $want: SKIPPED"; skipped=$((skipped+1)); return 0; fi
  if [ "$DRY" = "0" ]; then git push "$REMOTE" --delete "$b" && deleted=$((deleted+1)); else echo "DRY     git push $REMOTE --delete $b   # tip $want"; fi
}

# ---- A. 46 branches whose PR is MERGED and whose tip equals the PR head (merged-by-squash; C-61 table) ----
# #2 merged 2026-10-03 | tip=PRhead cdbe9c0 | main-only/branch-only 52/2 | squash-merged
del 'feat/field-core-gate-1.2-lockstep' cdbe9c021568cd634c5dd486f44920d62bb9fe7d
# #3 merged 2026-10-03 | tip=PRhead 474565f | main-only/branch-only 51/2 | squash-merged
del 'fix/ci-canary-scope' 474565f9ed6836640f0faaaa76db057104d6c1ba
# #4 merged 2026-10-05 | tip=PRhead 955b54c | main-only/branch-only 48/2 | squash-merged
del 'claude/field-op-console-features-o54e47' 955b54cd208269bbe098d7ef879435f2c7d72535
# #5 merged 2026-10-05 | tip=PRhead fb4b5f3 | main-only/branch-only 47/1 | squash-merged
del 'claude/fly-image-estate-probe' fb4b5f328f1e9be707330288edaaaa232cc168fe
# #7 merged 2026-10-12 | tip=PRhead eae2237 | main-only/branch-only 46/1 | squash-merged
del 'claude/defence-shield-incident-retro' eae22374f7f46d98bd46198c97c774ebcaf046f9
# #8 merged 2026-10-12 | tip=PRhead 40d7d6b | main-only/branch-only 45/2 | squash-merged
del 'fix/defence-shield-0.1.1-review2' 40d7d6b42e8868981cfb38c53e684bc3f77e78a9
# #9 merged 2026-10-21 | tip=PRhead b001447 | main-only/branch-only 44/2 | squash-merged
del 'claude/adr-0071-field-core-lockstep' b0014475dd1c3f3249071e11788bc3ebbfe9feb9
# #12 merged 2026-10-21 | tip=PRhead 3abeaef | main-only/branch-only 43/3 | squash-merged
del 'claude/adr-0072-estate-kill-watcher-r2' 3abeaef55936b726b4851319ef2cd96c74edc6e4
# #13 merged 2026-10-21 | tip=PRhead a2c33f7 | main-only/branch-only 43/4 | squash-merged
del 'claude/adr-0074-crosswalk-gate-controls-r2' a2c33f76dd3a27e1a955f74917ecc329d4948394
# #15 merged 2026-10-21 | tip=PRhead bfdd03e | main-only/branch-only 40/1 | squash-merged
del 'claude/probe-a2-signed-window' bfdd03e530c007f118086dafb17080ab9bcb370c
# #14 merged 2026-10-21 | tip=PRhead 1f661e7 | main-only/branch-only 41/1 | squash-merged
del 'claude/runbook-canary-grantor' 1f661e7963cd0a988f52eb5bf6e471ff4ea8a628
# #6 merged 2026-10-21 | tip=PRhead 219c4ca | main-only/branch-only 39/6 | squash-merged
del 'claude/state-fly-ops-console-0.2.0' 219c4ca2d0713b410b97078934820104e972ea4b
# #22 merged 2026-10-23 | tip=PRhead 93c447b | main-only/branch-only 34/1 | squash-merged
del 'chore/remove-stray-basetemp-dir' 93c447bfac17ae4d5854b4d4b555df2f6bda3b6d
# #24 merged 2026-10-24 | tip=PRhead 81755e6 | main-only/branch-only 31/1 | squash-merged
del 'claude/fix-time-of-day-flake' 81755e6f632934b6f32bb9054af6297fdae648a1
# #23 merged 2026-10-24 | tip=PRhead fcd0749 | main-only/branch-only 31/6 | squash-merged
del 'claude/phase-g-operator-auth' fcd07495a7365cd17d4bef9a9f28dedc8b240220
# #17 merged 2026-10-23 | tip=PRhead 01bd072 | main-only/branch-only 37/1 | squash-merged
del 'claude/runbook-a2-sentence-2026-10-23' 01bd0724ee404437ab4b2447ff3c02b6b1d32407
# #21 merged 2026-10-23 | tip=PRhead 266a2c5 | main-only/branch-only 35/4 | squash-merged
del 'feat/deployment-agent-skeleton' 266a2c5bc31d9166855fd76d8d0b268ddb8f7206
# #19 merged 2026-10-23 | tip=PRhead 0ecc968 | main-only/branch-only 36/2 | squash-merged
del 'feat/probe-registry-readonly' 0ecc9685de645e6fa4781cf1f6e0020d54905d24
# #20 merged 2026-10-23 | tip=PRhead bfc9aa5 | main-only/branch-only 36/3 | squash-merged
del 'test/redteam-ledger-mint-2026-10-23' bfc9aa5cd5f1ae82428dde731378e3d1ad8709d0
# #25 merged 2026-10-24 | tip=PRhead e94694e | main-only/branch-only 29/1 | squash-merged
del 'brand/ops-console-force-field' e94694ea4a62e05a7f2d9b4e561a13a3af4cea04
# #30 merged 2026-10-26 | tip=PRhead 1e723b9 | main-only/branch-only 24/5 | squash-merged
del 'feat/gb10-caddy-tls-internal' 1e723b96d7f5f079dba1cdbc73137bec7962ee5c
# #26 merged 2026-10-25 | tip=PRhead 8d99691 | main-only/branch-only 28/3 | squash-merged
del 'feat/operator-auth-plumbing' 8d99691300fed9038c7b0ebc827c97bb16470927
# #27 merged 2026-10-25 | tip=PRhead 927f8d5 | main-only/branch-only 28/2 | squash-merged
del 'feat/ops-console-setup' 927f8d5d0545fd629ec5a4513a6162d4e35c9720
# #33 merged 2026-10-26 | tip=PRhead 1a1328a | main-only/branch-only 25/4 | squash-merged
del 'feat/pg-s0-clients' 1a1328a0597706eb99c3fe520606a84395188200
# #29 merged 2026-10-26 | tip=PRhead b5229a1 | main-only/branch-only 25/2 | squash-merged
del 'feat/pg-s0-compose' b5229a1dfed40574af76b041ef20478557724a60
# #31 merged 2026-10-26 | tip=PRhead e015a3a | main-only/branch-only 24/3 | squash-merged
del 'fix/upgrade-smoke-isolation' e015a3a4e4fc6affd91f94452fc3679cc98f285c
# #37 merged 2026-10-26 | tip=PRhead 109a6ab | main-only/branch-only 19/3 | squash-merged
del 'docs/runbook-stage0-alignment' 109a6ab141da0baceb35d07968e5f3bedebe2f9a
# #36 merged 2026-10-26 | tip=PRhead 362c462 | main-only/branch-only 20/6 | squash-merged
del 'feat/pg-s0-cli' 362c462204db428f7ac96aebf7cabf5a953f48cb
# #32 merged 2026-10-26 | tip=PRhead 3a963c5 | main-only/branch-only 16/13 | squash-merged
del 'feat/pg-s0-core' 3a963c549e180e1ad65be78f7b77848c5de7c10d
# #42 merged 2026-10-27 | tip=PRhead 5339208 | main-only/branch-only 13/7 | squash-merged
del 'feat/pg-s0-followups' 5339208bf93a4a86784fc06ece4c6ce0a45f53e0
# #41 merged 2026-10-26 | tip=PRhead c921765 | main-only/branch-only 14/10 | squash-merged
del 'feat/pg-s0-guards-2' c921765d5749086181af3fcf4b98e389bcfa8931
# #34 merged 2026-10-26 | tip=PRhead 9c9baa3 | main-only/branch-only 21/3 | squash-merged
del 'fix/ledger-reader-rotation-window' 9c9baa30cfe24f9bfcfb4f53b93aa6dad341dc64
# #39 merged 2026-10-26 | tip=PRhead 9bdd46d | main-only/branch-only 17/2 | squash-merged
del 'fix/small-followups' 9bdd46d0d0437a5b1e569d5568425c41e4907606
# #38 merged 2026-10-26 | tip=PRhead 5894ccc | main-only/branch-only 19/1 | squash-merged
del 'fix/topology-lint-etxtbsy' 5894ccce7e4227644b493f6ae866e354d51b341c
# #50 merged 2026-10-27 | tip=PRhead fa95f96 | main-only/branch-only 5/5 | squash-merged
del 'feat/c20-console-key-transport' fa95f96c7342cea70cbefa00f47e3b2ccfddefe2
# #48 merged 2026-10-27 | tip=PRhead 731d527 | main-only/branch-only 8/1 | squash-merged
del 'feat/field-agent-fieldclient' 731d527187d22f101287d2424ed1a073edf9888a
# #53 merged 2026-10-28 | tip=PRhead 0db2106 | main-only/branch-only 4/2 | squash-merged
del 'feat/kr-r1-format2-parser' 0db210602164cf05f46a47ba61a9c1f0dbc44263
# #54 merged 2026-10-28 | tip=PRhead 7c0b99f | main-only/branch-only 1/10 | squash-merged
del 'feat/kr-r2-verify-hash' 7c0b99fdffc83ae403150c724957d7ae7f519ae1
# #51 merged 2026-10-28 | tip=PRhead f8f836f | main-only/branch-only 4/1 | squash-merged
del 'feat/kr-r3-lifecycle-headers' f8f836f112b9ba4b3a4c1556e1aff7c5368bde58
# #44 merged 2026-10-27 | tip=PRhead 562cb32 | main-only/branch-only 12/3 | squash-merged
del 'feat/pg-c5-fly-identity' 562cb32b1634dc25ffcdf9849a7cb74ac42e5c02
# #46 merged 2026-10-27 | tip=PRhead fbfcc28 | main-only/branch-only 12/5 | squash-merged
del 'feat/pre-stage3-followups' fbfcc28cc1793a8532fb1e7bacb9f7be69d6d119
# #43 merged 2026-10-27 | tip=PRhead 16a5576 | main-only/branch-only 12/5 | squash-merged
del 'feat/price-book-55-session-ids' 16a5576f4900c1eca146a378d0be3b2e7f97fa64
# #49 merged 2026-10-27 | tip=PRhead ab19ddd | main-only/branch-only 8/4 | squash-merged
del 'fix/doa-roster-job-rows' ab19ddd0a4b51eb48fa095531f086c2f980491de
# #47 merged 2026-10-27 | tip=PRhead 1203d4d | main-only/branch-only 8/3 | squash-merged
del 'fix/ledger-verify-missing-path' 1203d4df35d8665bfc9b99fab6fdbe7bbb577627
# #52 merged 2026-10-28 | tip=PRhead 41284d7 | main-only/branch-only 4/3 | squash-merged
del 'fix/signed-operator-ledger-events' 41284d79253e8aa36f0f12b455838f260306b9e0
# #45 merged 2026-10-27 | tip=PRhead a5ee1a7 | main-only/branch-only 12/7 | squash-merged
del 'fix/stage0-hardening-pins' a5ee1a72ff2decf05406a1e52de555b9b42a8a1e

# ---- B. 3 branches whose PR was CLOSED unmerged and superseded (C-62 evidence: see 20261028-1530-reviewer-c62-loose-ends.md) ----
# #11 closed 2026-10-21 unmerged | tip=PRhead cc68dc1 | main-only/branch-only 44/5 | tree identical to successor #12 (git rev-parse tree equal)
del 'claude/adr-0072-estate-kill-watcher' cc68dc1cf80589d9239f8b853330af8b1466495c
# #10 closed 2026-10-21 unmerged | tip=PRhead edf22f3 | main-only/branch-only 44/3 | 14 lines dropped on purpose: #13 body says the FC-E-04 Art.14 partial citation became pending
del 'claude/adr-0074-crosswalk-gate-controls' edf22f3c2091ca103b0b6d5509569b7ba0d56b36
# #40 closed 2026-10-26 unmerged | tip=PRhead a15e893 | main-only/branch-only 16/19 | superseded by #41 (title); 77 of 4428 added lines absent from main, sampled ones traced to later changes: MEDIUM, tag first if in doubt
del 'feat/pg-s0-guards' a15e893ec14e1885fcd6650736c1f5c373a19574

# ---- C. (optional, from C-9/C-39/C-59) four earlier squash-merged branches; uncomment to include ----
# #16 MERGED, tip = PR head
# del 'ci/harden-workflows-2026-10-23' 4331864a5dbc27cbf4bd27e673aa9db4a7ae5f17
# #18 MERGED, tip = PR head
# del 'ci/topology-lint-2026-10-23' fd5980785b6dd3752f8e561a8dfe30159759949c
# #28 MERGED, tip = PR head
# del 'feat/phase-g-check-tool' fb80a317e0d86a1302d7bfba455769c9d250d6fb
# #35 MERGED, tip = PR head
# del 'feat/claude-approver-v0' 9f1f4ee2b33eaf83a4c7a3927f655d3c08d8a9bc

echo "done: deleted=$deleted skipped=$skipped (DRY=$DRY)"
