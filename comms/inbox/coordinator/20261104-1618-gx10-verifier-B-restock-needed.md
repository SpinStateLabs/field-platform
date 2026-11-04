# restock-needed: verifier (also builder and reviewer show unclaimed=0)

- dispatch.sh level at the time: builder unclaimed=0 RESTOCK, reviewer unclaimed=0 RESTOCK, verifier unclaimed=0 RESTOCK. The verifier worklist is empty after verifier B finished its items (PRs 342, 368, 421, 425, 443, 462, 466, 474, 487, 426, 450, 478, 479, 514, 525, 583, 578, 570, 617, 562, 549, 610, 602, 585, batch m1a).
- Running the verifier FALLBACK now: full 16-suite run on current main, to give the first main-equivalent baseline since cd3b7690 and to report any count that went down.
- Worth carding: re-runs of the red-by-c57 PRs (583, 578, 570, 617, 562, 549, 610, 602, 585) after they are rebased onto main b963407a, since each of those reports ends "needs a re-run to confirm green".
