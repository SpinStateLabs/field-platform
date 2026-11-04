B-S2-19 -> draft PR "lifecycle-manager: malformed roster is 422/503 not 500; junk FIELD_LIFECYCLE_EVERY warns (S2-19)".
HIGH: 11/16 new tests fail pre-fix, 16 pass post-fix; 73 api/roster tests pass; env-doc/anchors 98 pass.
NEEDS DON: (a) changing two tests that pinned 500 -> 503/422; (b) 60 s env floor is my proposal.
MEDIUM: full lifecycle suite not run end-to-end locally; overlapping open lifecycle PRs may conflict on api.py.
