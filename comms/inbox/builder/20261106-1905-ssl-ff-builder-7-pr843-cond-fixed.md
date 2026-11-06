# ssl-ff-builder-7: B-PR843-ci-anchors done (PR 843)
Condition fix pushed on the PR's own branch. New head: 177e4ce8e09b425164eaf57a8dd35ec8e71e5c4a (was 2e696cd0). Identity: author AND committer Don Hagell, trailer Sonnet 5.5, nothing under .github/.

docs/ENVIRONMENT.md only: python tools/environment_anchors.py --fix moved FIELD_OPERATOR_REGISTRY to :71 and FIELD_OPERATOR_REQUIRE to :72; --check 0 wrong rows; test_ci_anchors_step_c1191 and test_environment_anchors_c1116 42 passed. No code change. Docs-only delta for the reviewer re-pass. Not run: CI, GX10.
