# C-1128 PR 442: main merged in (builder Lane 13)

Auto-fix reported a conflict with main. Merged origin/main b39287c1 into the PR branch (no rebase, no force). New head 6385f8772a702eaf049b8d12cf33d524e81b1008; contains main (HIGH). One conflict, tools/tests/test_422_handler_installed_c1114.py: kept my Call-node guard and main C-1158 field cases. Tests: guard file 26, agent-registry 49, federation-broker 422 test 3, environment_anchors --check 0 wrong (HIGH). GX10 not run.
Open for coordinator: C-1158 says every 422 carries a fixed reason; federation-broker still keeps its validator messages (F3 reading). Does C-1158 cover it? (I do not know.)
