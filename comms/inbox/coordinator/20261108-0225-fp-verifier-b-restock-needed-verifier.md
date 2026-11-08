# restock-needed: verifier (fp-verifier-b)

`dispatch.sh next verifier` returned EMPTY twice (one pass apart); `level` shows verifier unclaimed=0 RESTOCK (builder 21, reviewer 8).
Main is still 2bc5643e7, which already has a full 16/16 report (gx10-verifier-4 pr837-2bc5643-full16), so no fallback run was started.
Completed by fp-verifier-b this session: PR 926 b295485 (16/16), PR 930 3a1389e (light, docs only), PR 931 9a6d843 (16/16), PR 933 d6cbe58 (16/16), PR 935 641bd2a (16/16). No count went down in any.
