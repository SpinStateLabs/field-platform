# Builder Lane 1: claim C-504 (transport exception text at the HTTP boundary)

No unclaimed builder card is left except cards on others' PRs and PR 57. C-504 is unblocked (C-503 is on main) and still open: on main the kill-switch API puts the transport exception text into a 502 reply at six sites (api.py around :520, :536, :608, :689, :705, :739), the lifecycle API at :464, and the ops-console at :102 and :109. One PR from main, one commit, type name only, a canary test per site. C-505 (the AST lint) follows once C-504 is reviewed. Overlaps checked in the PR text (336, 348, 381, 372).
