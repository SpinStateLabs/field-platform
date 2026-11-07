# ssl-ff-builder-9: B-COND-PR828-e1474ce -> no change to PR 828 (closed as done, no builder fix exists)

Verdict (ssl-ff-reviewer-8, head e1474ce): PASS WITH CONDITIONS, no bypass found. Both conditions are not code fixes to this PR:
C1 (rollout): no service passes `write_only_paths` or `service=`; before any deployment sets FIELD_READ_KEY, a separate card must audit each of the 16 services' GET routes, pass those arguments where needed and add a per-service test that a read key is refused on write-like GETs. That is new work across 16 services, not an edit to PR 828; I did not start it without a card. Suggested card: B-RT-readkey-per-service-audit (one service per sub-card is the safe size).
C2 (coordinator): merge order versus PR 490 and a non-ASCII key test on whichever lands second. Not mine to decide.
Nothing pushed; PR 828 head unchanged.
