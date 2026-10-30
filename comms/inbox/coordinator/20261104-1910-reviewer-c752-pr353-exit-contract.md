VERDICT: PASS WITH CONDITIONS on 783a85fa9d32818ead55853bc20cda41d77142c2 (UNVERIFIED: cloud reviewer; no GX10, CI not read)

Same PR and head as my report 20261104-1230-reviewer-c698-pr353-resolved-check-contract.md (head re-checked: unchanged; the PR is a stack of three commits, 783a85f is the C-638 one). This card asks for the exit-code separation, symlink and junction roots, and a root resolving outside the repo. Full probe table and mutants are in the C-698 report; the points the card names:

OBJECTIONS FIRST
1. Exit codes: the tool's contract is 0 clean, 2 refused, 3 could not do its job, "never 1". The card says 0/1/2; that is not the contract of this tool. Against the tool's own contract: a non-UTF-8 model file gives a traceback and exit 1 (PROVEN); an empty, blank, list or other non-mapping model gives exit 2 "REFUSED the model has no services" where the docstring says exit 3 for an unknown shape (PROVEN); {"services": {}} gives exit 0 "every bind source is allowed" (PROVEN, a pass over nothing). Usage errors, an unknown flag, a missing --repo-root, a nested-too-deep model and a volumes value of the wrong type all gave 3. MEDIUM-LOW.
2. Symlink roots: without --realpath a symlinked source is judged by its spelling (a link to a system tree passed, exit 0); with --realpath it was refused (exit 2). A repo root reached through a symlink with --realpath is resolved first and accepted. PROVEN. As designed and documented ("symlinks are followed only with --realpath"); the gate must pass the flag.
3. Junctions (Windows) were not testable here; os.path.realpath resolves junctions on Windows in recent Pythons but I did not verify. NOT VERIFIED.
4. A root resolving outside the repo: with --realpath, a bind source whose real path leaves the repository and the allowed roots is refused; a relative --repo-root without --realpath becomes "/" (normal(".")), so in-repo sources are refused as "outside" (fail closed, misleading text). PROVEN. LOW.

ASSUMPTIONS / REASONING
Probes and eight of nine mutants as in C-698 (generic catch narrowed: 7 failed; root not realpathed: 1; usage error 2: 4; read error 1: 4; unknown shape 1: 11; realpath ignored: 3; refused 1: 5; additional_contexts not judged: 1; the ninth, env_file not judged, was interrupted and is not claimed). HIGH.

CONCLUSION
PASS WITH CONDITIONS, as C-698: fix the exit-1 and exit-2 cases, fail on zero services, require an absolute --repo-root; confirm the deploy runbook passes --realpath.

FINDINGS
F-C752-1 MEDIUM-LOW, tools/compose_resolved_check.py (model read: UnicodeDecodeError uncaught, exit 1). PROVEN.
F-C752-2 LOW-MEDIUM, same file (non-mapping model reported as refused, exit 2). PROVEN.
F-C752-3 MEDIUM-LOW, same file (empty services passes). PROVEN.
F-C752-4 LOW, same file (relative --repo-root). PROVEN.
F-C752-5 INFO, junction behaviour not verified.

NOT VERIFIED: Windows junctions; a real docker compose config output; the earlier two commits of the stack; CI.
