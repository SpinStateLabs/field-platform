# reviewer Lane 15: Q-132, PR 484 (C-1206, field_agent.actions pinned as a module), head d43f7ec1246be39e3c041c2a2c9a12fe9e4a9a7d

VERDICT: PASS on d43f7ec1246be39e3c041c2a2c9a12fe9e4a9a7d, low risk, with one LOW pin gap (F-Q132-1). Head re-read with git ls-remote refs/pull/484/head at claim time and again before this note, unmoved. 1 commit on main cd3b7690 (contains main), author and committer Don Hagell noreply. One file added, `packages/field-agent/tests/test_actions_surface_c1206.py`, +53/-0, no source change (git diff --stat). Not Lane 13. Local Windows run, relative PYTHONPATH (";" separated), PYTHONUTF8=1, no stdin, scratch worktree, read-only on the PR. Not a GX10 run, GitHub CI not read. No estate value in this note or in the file.

## OBJECTIONS FIRST (limits)
1. The module under test is nine lines (an import of four names and an `__all__`); mutants on it say little about the rest of field-agent.
2. The test that claims "no class, function or assignment of its own" reads only the top level of the file, so it cannot see a definition hidden inside an `if` or a `try` (F-Q132-1).
3. A first run of the whole package from the repository root gave 3 collection errors (`No module named 'tests'`) in three other test files. That was how I started pytest (from the root, not from `packages/field-agent`), not the PR: run from the package directory the whole suite passes on the head (212 passed, 393 s). I did not finish the same run on clean main, so I do not claim a main baseline.

## THE QUESTIONS (from the card)
1. THE FIVE TESTS ASSERT WHAT THE TITLE SAYS AND ARE NOT VACUOUS. HIGH. Read against `actions.py` and the sentinel's `governed` module: (1) `sorted(actions.__all__) == sorted(NAMES)`, the four names; (2) each name `is` the sentinel's own object (identity, not equality), so a copy or a subclass fails; (3) the package exports the same objects and lists the names in its own `__all__`; (4) an AST walk of the top level finds no class, function, or assignment other than `__all__`; (5) three made-up names (Blocked, check, verdict) are absent. Measured by mutants below: the surface, identity, and own-definition tests each die under their own mutant.
2. MUTANTS ON field_agent/actions.py. Baseline 5 passed. 15 mutants: 8 KILLED by a failing assertion, 1 broke at collection, 6 SURVIVED.
   - KILLED (8): a name dropped from `__all__` (A1); an extra name in `__all__` (A2); `ActionBlocked` redefined locally (A3); `Governor` subclassed locally (A4); a private assignment added (A5); a helper function added (A6); an unknown attribute provided (A7); a module `__getattr__` that answers any name (A8).
   - BROKE AT COLLECTION (1): A15, the re-export taken `as _g` (a rename). pytest exited with a collection error (rc 4) because the package import fails, so it is a break, not an assertion; I count it as caught but not as proof of a test.
   - SURVIVED, EQUIVALENT (2): `__all__` reordered (A9) and `__all__` made a tuple (A10). The test compares sorted names on purpose, so order and container are not part of the contract.
   - SURVIVED, REAL GAPS (4): an import added (A11); a bare statement with a side effect (a print) added (A12); a class hidden inside an `if` (A13); a function hidden inside a `try` (A14). See the finding.
   Lane 13 reports the mutants were run by hand with one close survivor; I did not re-run its set, mine is independent.
3. NO ESTATE VALUE. HIGH. The file reads nothing from the environment (it says so in its docstring and a grep for environ and getenv finds nothing), opens no connection, and uses no value besides the four class names and three made-up attribute names.

## RESULTS
- New file: 5 passed (1 warning). The whole field-agent suite, run from `packages/field-agent`: 212 passed, 1 warning.
- The scratch worktree is clean after the runs; every mutant was restored.

## FINDINGS
- F-Q132-1 LOW (pin gap, the "defines no class, function or assignment" test): the AST walk checks only `tree.body` for ClassDef, FunctionDef, AsyncFunctionDef and Assign-like nodes, so four additions pass the suite: an import (A11), a bare expression such as a print (A12), a class inside an `if` (A13), and a function inside a `try` (A14). The test's own docstring says "imports and one __all__ list, nothing else", and the module docstring says "the SDK adds no verdict logic of its own"; an `if` block that defines a class would be exactly such logic and the suite would not see it. Measured: each of the four passes all 5 tests. Pin: walk the whole tree with `ast.walk` for ClassDef and FunctionDef, and assert that the top-level statements are only the docstring, `ImportFrom`, and the one `__all__` assignment (so `Import`, `Expr`, `If` and `Try` fail).
- Note (no action): A9 and A10 are equivalent by the test's design.

## CONCLUSION
PASS on d43f7ec1: five tests that assert the public surface, object identity, the package re-export, the absence of top-level definitions and of invented attributes, with no environment or network use; 8 of 15 mutants die by assertion, 1 breaks the import, 2 are equivalent, 4 are a LOW gap that the test's own docstring over-claims. What this PASS does not cover: GitHub CI and GX10 on this exact head (none from me), a main baseline for the whole package (not finished), and the rest of field-agent. After this PASS builders do not push to the branch (head-freeze); the pin above can go in a follow-up PR.
