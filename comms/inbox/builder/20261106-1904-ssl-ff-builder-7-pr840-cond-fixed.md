# ssl-ff-builder-7: B-PR840-pin-services-rt832 done (PR 840)
Condition fix pushed on the PR's own branch. New head: 394d09aaa576ad53de4c858a0735dfbb8dca79b0 (was baa599aa3). Identity: author AND committer Don Hagell, trailer Sonnet 5.5, nothing under .github/.

C1 literal pins of the Stage 1/3 eight and the Stage 2 pair: R2f, R2g die. Empty expected_services (None, (), [], '') now means the stage list (R2h dies); an override naming a non-compose label (for example federation) raises ValueError, so a Stage 0 label is refused loudly. Nothing-armed abort record pinned (R4d dies). C2 stays a coordinator note: driver counters() keys must equal the compose names. test_stage_controller.py 148 passed (venv); anchors 0 wrong. Not run: CI, GX10.
