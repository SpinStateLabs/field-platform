builder-1: B-REBUILD-PR339 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/548 "rebuild of #339", branch rebuild/pr339-innerhtml-audit, head 668c70d616d3fa28f616a4b13a2008bb591ae5fe on origin/main 97dcfec1. Old head 0219998a untouched.
Conflict-free: 3 commits cherry-picked, range-diff shows all three patches identical (=). Only the ops-console audit test files change.
Ran from services/ops-console, relative PYTHONPATH: tests/test_innerhtml_audit_c457.py 190 passed (node 22).
Range-diff:
1:  097814dc = 1:  591eef59 ops-console tests: the innerHTML audit reads every script type, scopes esc, rejects templated handlers and covers more sinks (C-457 follow-up, reviewer C-508 F-C508-1..4)
2:  ab709ed9 = 2:  9632ffaf ops-console tests: the innerHTML audit finds script blocks the way an HTML tokenizer does and fails on an unextracted opener (C-620 F-C620-1)
3:  0219998a = 3:  668c70d6 ops-console tests: the innerhtml audit uses the HTML whitespace set in its script lookaheads (C-673, reviewer C-657 F-C657-1)
