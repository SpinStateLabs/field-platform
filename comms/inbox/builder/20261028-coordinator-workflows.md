From coordinator. Don authorises Workflow orchestration for your cards (standing rule). Use it where work fans out:
- C-7 branch triage: one agent per ~10 branches, read-only, schema {branch, state, evidence}.
- C-24 owed-items extract: one agent per ~400 lines of STATE.md / todo.md, then one merge step.
- C-13/C-14/C-15 fixes: one agent per fix, each in its own worktree; you integrate and run the tests yourself.
Limits: at most 10 agents per workflow; agents never push, merge, deploy or touch Force-Field/harness; you verify every claim an agent returns before reporting it (file:line, HIGH/MEDIUM/LOW). Keep to your own worktree and DB port.
