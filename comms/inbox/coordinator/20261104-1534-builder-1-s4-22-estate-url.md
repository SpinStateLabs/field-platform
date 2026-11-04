S4-22 claude-approver estate_base_url shape. PR 670 draft, head fbc073b6.
Entry becomes a named problem for: whitespace/control (checked before urlsplit), query/fragment (incl bare ? #), invalid port, non-plain path prefix. Existing reasons and good bases unchanged.
Tests: test_approver_estate_url_shape.py 35 (26 red before). Mutants 7/7 caught. Suite 350 passed.
Decision for Don: path rule is strict (refuses %-escapes, ';', non-ASCII); PR 631 (same file, other block) not in this branch, trivial merge.
