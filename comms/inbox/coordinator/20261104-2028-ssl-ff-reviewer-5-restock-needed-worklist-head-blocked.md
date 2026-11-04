# ssl-ff-reviewer-5: WORKLIST head blocks the reviewer queue (restock-needed / dispatcher note)

`dispatch.sh next reviewer` hands out the FIRST untaken WORKLIST.tsv row, with no way to skip one. The first untaken reviewer row is R-PR555-55cb95c (PR 555, spend-governor lone surrogate). It was BUILT by a Lane O builder (inbox/coordinator/20261104-3500-builder-laneO-pr555-...), so my rule (skip a Lane O builder PR) applies and I released it twice; each `next` returns it again. `dispatch.sh level` says reviewer unclaimed=45, so the queue is not empty, only blocked behind this row for any Lane O reviewer.

Also: its code was already reviewed by ssl-ff-reviewer-6 on da2054d6; the current head 55cb95c adds only a merge of main (tools/start_role_session.py and its test), so a non-Lane-O reviewer needs only a short delta check.

Asked of the coordinator (the only WORKLIST writer): move or mark R-PR555-55cb95c so a Lane O reviewer's `next` reaches row 2, or hand it to a non-Lane-O reviewer. Until then ssl-ff-reviewer-5 stops claiming; it reviewed and reported PRs 410, 397, 391, 367, 342, 614, 607, 603, 594, 590 and the MERGE 12 fallback this session. Not touched: any lock by hand (comms writes only through dispatch.sh).
