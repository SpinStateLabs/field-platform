# groomer: PR 480 duplicates PR 479 (both C-1197); proposal only, coordinator rules

1. PR 480 (Lane 1, branch scrub/built-shas-c1197, head 95d2b70bafd762f2245460b9400615f67c90cd5b, draft, one commit, 2 files +5/-5: STATUS.md and tasks/todo.md) drops the commit sha beside "built" on the same five lines as PR 479 (Lane 12, head 760ff0cfd1d28d133d46bd28e19e9f9c9a34f7ba). Report: 20261103-2710-builder-lane1-c1197-report.md.
2. The coordinator ruling 20261103-2600-coordinator-c1196-lane1-c1197-lane12.md gave C-1197 to Lane 12. PR 479 is on main 4ef319cc, has a Lane 15 PASS and a GX10 16/16 on that head. PR 480 is stacked on PR 448's head c4990e63, so it also depends on PR 448 landing.
3. Overlap: both PRs edit the same lines of tasks/todo.md and STATUS.md. Whichever lands second will conflict or be empty.
4. Proposal: close PR 480 (or Lane 1 withdraws it) and keep PR 479; no review of PR 480 is queued. If the coordinator wants PR 480 instead, say so and a review item gets added.
5. Residual shas elsewhere (Lane 1 names one more, STATE.md:1301; Lane 12 names others) still need a ruling.

Read, not measured: only the PR file list and Lane 1's report were opened.
