# ssl-ff-builder-9: B-COND-PR455-166db1c -> pushed to PR 455

PR 455 new head 89d3cfadea16e4726c02406240cb813548100be1 (tests only, one commit on 166db1c82; author AND committer Don Hagell noreply; remote verified).
C1: defence-shield/agent-incident-retro/tests/test_clauses.py: test pins CONTEXT_BENIGN == 20 and the edge (21 benign before a hostile request keeps lines 2..21 plus the hostile; 19 benign keeps all). Mutants B4 (19) and B5 (21) KILLED. Package tests: 270 passed, 2 skipped (with field-core on the path).
Not run: CI; GX10 16/16. The observation that tools/tests/test_public_safety_c560.py does not exist at this head stands (not mine).
