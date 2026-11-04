# Report: S-B6 (scout round 2), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or comms note for blank registry fields.
PR 511 (draft): https://github.com/SpinStateLabs/field-platform/pull/511, branch fix/registry-blank-owner-name-domain-sb6, head c42b3488afd83d784058823df869ee3dccd2500c (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane B: registry).
Bug (R, 40 red tests): AgentCreate/AgentUpdate accepted whitespace-only name, owner and domain (and domain "" on create and PATCH); a padded domain is stored padded. The kill-switch domain-halt consequence (a halt for "finance" missing " finance") is inference, I did not read the kill-switch matching.
Fix: strip and require non-blank on AgentCreate/AgentUpdate only; AgentRecord (read model) deliberately untouched so a legacy row still reads back. Behaviour change: padded values are now stored stripped. 46 tests; registry 357, lifecycle-manager 269, kill-switch 270 passed; anchors --check 0 wrong (run before push); two mutants killed (38 red, 2 red).
Not investigated (possible follow-up cards): domain case-folding; no agent_id length cap (a 200-char slug is accepted, from S-B7).
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511; none merged by me.
Scout round 2 not taken: S-A6, S-B4, S-B5.
