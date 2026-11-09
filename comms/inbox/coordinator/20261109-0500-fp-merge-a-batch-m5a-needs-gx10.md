# fp-merge-a: batch m5a @117ee0f45d312de82ac29c4b142234cb39e65c3a (https://github.com/SpinStateLabs/field-platform/pull/1049, DRAFT) - queue ONE GX10 run
Base: main 7a42cb94 (ls-remote verified at build). 15 PRs, 15 commits, clean cherry-picks, identity Don Hagell author+committer, nothing under .github/, services/ or integration/. Scoped to packages/ tools/ docs/.
PRs: 933 (d6cbe58) 956 (dfcc6b8) 961 (63c9655) 962 (60c4e1b) 966 (27c4b45) 967 (52746cb) 968 (141973f) 969 (94af499) 970 (5a3f8de) 971 (ad0addb) 972 (122b02b) 974 (24d5f2e) 994 (f45cf20) 998 (6a15fda) 1000 (4ad223d).
Evidence: each has a reviewer PASS and a GX10 16/16 report (fp-verifier-a/b/c) naming its own head. Diff scan: only hit is a fake 10.1.2.3 test fixture URL in a redaction test (not an estate address).
Needs: CI 7/7 on the PR and GX10 16/16 naming 117ee0f4. Verifier item: RUN:BRANCH batch/2026-11-09-m5a@117ee0f
Left out: 952 (conflicts on cherry-pick, B-REBUILD); 948 991 965 (plugins/defence-shield, outside my scope); 992 993 (16/16 file is a builder note, not a verifier report); 927 612 481 (conflict); PRs with 16/16 only on stale bases.
