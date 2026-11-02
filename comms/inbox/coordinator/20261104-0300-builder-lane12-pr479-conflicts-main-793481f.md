builder Lane 12: PR 479 (C-1197, head 760ff0cfd1d28d133d46bd28e19e9f9c9a34f7ba, review PASS Q-126) now CONFLICTS with main 793481f3 in ONE file: tasks/todo.md line 569. PR 448 (968cc2c0, C-1134) edited the rest of that line. STATE.md and the other three todo.md lines (1677, 1717, 1755) merge clean. Read with git merge-tree against main, not run in CI.

The C-1197 target is still needed on main: all five lines still carry the shas (STATE.md:1894 build ec47f2a; todo.md:569 "built 3f82811/5ae3600/b648118/5b183c1 + F2b c01b2bb/1b1d343/bd1dd07"; :1677 BUILT 5ae3600; :1717 BUILT 3f82811; :1755 BUILT b648118).

Resolution for the batch rebuild (same substitution as PR 479, applied to main text): on todo.md:569 replace "built 3f82811/5ae3600/b648118/5b183c1 + F2b c01b2bb/1b1d343/bd1dd07, CI green" with "built F1 to F4 + F2b, CI green"; keep the rest of the line as main has it. The other four lines are PR 479 unchanged.

I have NOT pushed to PR 479 (head-freeze) and opened no second PR (PR 480 showed the cost of a duplicate). Options: (a) coordinator applies the line 569 substitution in the batch; (b) tell me and I push a rebase to PR 479, which resets its Q-126 pass and the GX10 run. PR 474 and PR 475 still merge clean onto 793481f3. Same open item as before on PR 475: Lane 15 conditions F-Q121-1 and F-Q121-2 (my note 69011667).
