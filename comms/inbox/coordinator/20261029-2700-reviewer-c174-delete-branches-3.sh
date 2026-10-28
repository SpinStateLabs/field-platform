#!/usr/bin/env bash
# C-174: THIRD delete-list for remote branches of SpinStateLabs/field-platform (everything squash-merged, an ancestor of main, or closed-superseded).
# AUTHOR: teammate-don-reviewer, 2026-10-29, main 7b4d6f7533fe94fd42cea1f79149a4ed1a863ff5. NOT RUN by the author. For DON'S APPROVAL; the coordinator runs it, never the reviewer.
# Same safety rules as the C-63 and C-74 scripts: dry-run by default (DRY=0 to execute); each branch is deleted only if its remote tip STILL equals the sha recorded here;
# main, comms and the live branches are refused. Excluded on purpose (live / open PR): feat/kr-r4a-rotator-core (#57), fix/renew-token-signed, fix/operators-loader-c178 (#93), fix/registry-retired-store-guard-c167 (#92).
# New in this script: each branch is also refused if it has an OPEN pull request right now (gh pr list --head), when gh is available.
# Recovery: git push origin <sha>:refs/heads/<branch> (shas below); for PR heads refs/pull/<n>/head also stays on GitHub.
set -euo pipefail
REMOTE="${REMOTE:-origin}"; DRY="${DRY:-1}"
PROTECTED="main comms feat/kr-r4a-rotator-core fix/renew-token-signed fix/operators-loader-c178 fix/registry-retired-store-guard-c167"
deleted=0; skipped=0
del() {  # del <branch> <recorded-tip-sha>
  local b="$1" want="$2"
  for p in $PROTECTED; do [ "$b" = "$p" ] && { echo "REFUSE protected: $b"; return 1; }; done
  if command -v gh >/dev/null 2>&1; then local n; n="$(gh pr list --head "$b" --state open --json number --jq length 2>/dev/null || echo 0)"; [ "${n:-0}" != "0" ] && { echo "REFUSE open PR on $b"; return 1; }; fi
  local got; got="$(git ls-remote --heads "$REMOTE" "refs/heads/$b" | cut -f1)"
  if [ -z "$got" ]; then echo "ABSENT  $b (already deleted)"; skipped=$((skipped+1)); return 0; fi
  if [ "$got" != "$want" ]; then echo "MOVED   $b tip is $got, recorded $want: SKIPPED"; skipped=$((skipped+1)); return 0; fi
  if [ "$DRY" = "0" ]; then git push "$REMOTE" --delete "$b" && deleted=$((deleted+1)); else echo "DRY     git push $REMOTE --delete $b   # tip $want"; fi
}

# --- A. tip is an ANCESTOR of main 7b4d6f7 (git merge-base --is-ancestor true): nothing on the branch is missing from main (18) ---
# PR 70 MERGED
del 'batch/2026-10-29-a' 45a36f5cf70db9d80a1cc82aabb0c7d8fcec8f61
# PR 73 MERGED
del 'batch/2026-10-29-b' 0b44deea8689c63a32731bd9df05aae6109b611e
# PR 89 MERGED
del 'docs/crosswalk-readme-c139-r2' 4cf73d57a60c072f666da923631a8044457f7443
# PR 59 MERGED
del 'feat/alerts-ntfy-r2' c6883e56d47c29cf3fd3e7952d69ce24fffa3b52
# PR - no PR
del 'feat/machine-verifier-identity-r3' 151cd3fa21f0cfb30feb20b1376708440995242e
# PR 64 MERGED
del 'fix/breakglass-alias-format1' a8bd47c67b507053d3d2177d03bb546e7b326ad8
# PR 63 MERGED
del 'fix/breakglass-alias-squat-r2' 84d26a49db859c82b5526f15c622bb95c243f95f
# PR 58 MERGED
del 'fix/breakglass-must-be-sealed' 75a84c8f93578e23eb6403a82b3140b45723a694
# PR 75 MERGED
del 'fix/gateway-followups-r2' 92922465b9362e2ac9a9d0f0fd6e40f74c80faab
# PR 61 MERGED
del 'fix/observer-witness-content-edit-r2' aaae5ece47d69fc4be4d9a9eb35228fac3ef67ca
# PR 66 MERGED
del 'fix/refused-record-drop-counted-r2' a91b8194c35a0641913bec67859f12c1b683a24d
# PR 91 MERGED
del 'fix/registry-retired-terminal-c161-r2' 7b4d6f7533fe94fd42cea1f79149a4ed1a863ff5
# PR 83 MERGED
del 'test/kill-switch-drill-detection-r2' 15a7304d5a3ad44c1707f4d7a8e694094cb4191d
# PR 85 MERGED
del 'test/liveness-cutoff-r2' b92ec10136601b02e753e1fb363b8aafa2c9c139
# PR 79 MERGED
del 'test/operator-health-survivors-r2' ad33a601041360b29d923b7da0639ca7b973c969
# PR 87 MERGED
del 'test/rename-retry-c136-r2' 70fa59f7a455e59bd05260c688fc468812700c78
# PR 77 MERGED
del 'test/revoke-refusal-record-r2' 444e49b828c9cc1dbdb579a966c98d7808248a30
# PR 81 MERGED
del 'test/spend-governor-windows-r2' 284f14ba48dd7933fb8be4e2ae5eada8e61132eb

# --- B. CLOSED pull request, not an ancestor of main, superseded by a merged successor (19); successor named per line ---
# PR 88 CLOSED; superseded by #89 (docs/crosswalk-readme-c139-r2, merged 4cf73d5)
del 'docs/crosswalk-readme-c139' 79fccf80dbe864e71718420b6bdad42f887555cd
# PR 56 CLOSED; superseded by #59 (feat/alerts-ntfy-r2, merged)
del 'feat/alerts-ntfy' bebf0f1db8ed01eb7690ce7a2c3b7ab0f5e16757
# PR 55 CLOSED; superseded by #55 content: its 7 commits are patch-identical in batch B (#73, merged 0b44dee), C-110
del 'feat/machine-verifier-identity' 6e78f3195531b3cf7d7642bea405ac933b5d8a38
# PR 71 CLOSED; superseded by #71 content: batch B (#73, merged 0b44dee), C-114 patch-ids
del 'feat/machine-verifier-identity-r2' 4bbdf03149f731abafe6e5f42efcc3d3b40b6840
# PR 62 CLOSED; superseded by #63 (-r2, merged)
del 'fix/breakglass-alias-squat' 10fa36cdae56ed9727a4876a84dd8763a03d9cf3
# PR 67 CLOSED; superseded by #67 content: batch A (#70, merged 45a36f5), C-107 patch-ids
del 'fix/console-frame-headers' 4921611feb53a776498407e77705bd0a2a742592
# PR 68 CLOSED; superseded by #68 content: batch A (#70), C-107
del 'fix/fieldclient-no-env-proxy' 23a1b81a4d504622be3c58c566b7ed80f6574307
# PR 74 CLOSED; superseded by #75 (-r2, merged 9292246), C-115 addendum
del 'fix/gateway-followups' eb7c72108342945de7b9bc552f9e46c194c9ac8e
# PR 69 CLOSED; superseded by #69 content: batch A (#70), C-107
del 'fix/gateway-key-hygiene' f3126915d3710a9b253d870324b97dcbe650630d
# PR 60 CLOSED; superseded by #61 (-r2, merged)
del 'fix/observer-witness-content-edit' c71c8be1cdaa37ea14a3283db8baac88fec075cd
# PR 65 CLOSED; superseded by #66 (-r2, merged a91b819)
del 'fix/refused-record-drop-counted' 5ddabeb215d8e3cb8a4d030a932d000e174862b1
# PR 90 CLOSED; superseded by #91 (-r2, merged 7b4d6f7), C-166
del 'fix/registry-retired-terminal-c161' c90ebff58738a3cf6c29d872ee9b6fa4745098c3
# PR 82 CLOSED; superseded by #83 (-r2, merged 15a7304), C-134
del 'test/kill-switch-drill-detection' 1a97186470925c9147f0c993cb4a45a805adbaa2
# PR 84 CLOSED; superseded by #85 (-r2, merged b92ec10), C-140
del 'test/liveness-cutoff' c7a660779e1d3d0bbd7f3e885d1544d500bd2d92
# PR 72 CLOSED; superseded by #72 content: batch B (#73), C-114
del 'test/observer-deadline-primitives' 60bfa08ee6877f831dee9b00fb657d7c82ac7b92
# PR 78 CLOSED; superseded by #79 (-r2, merged ad33a60), C-123
del 'test/operator-health-survivors' 995865814b629015a41eb8745abef193213ada52
# PR 86 CLOSED; superseded by #87 (-r2, merged 70fa59f), C-154
del 'test/rename-retry-c136' 148838cfe86853c4918cab5c7d12c4c43a67e4c2
# PR 76 CLOSED; superseded by #77 (-r2, merged 444e49b), C-120
del 'test/revoke-refusal-record' 2bbfb9276156b448c9e06dd154146359e3d46553
# PR 80 CLOSED; superseded by #81 (-r2, merged 284f14b), C-131
del 'test/spend-governor-windows' 152cfde6c629591377deae95ad2a11e16f66e2ae

# --- C. no PR, not an ancestor of main, content already in main: test/observer-deadline-primitives-r2 (dc06e22): its single commit adds the same 81-line file as main's 0b44dee (batch B, #73); added-line text compared equal ---
del 'test/observer-deadline-primitives-r2' dc06e22dd1f25d31d956231f2d66a9c6a855132b

echo "done: deleted=$deleted skipped=$skipped (DRY=$DRY)"
