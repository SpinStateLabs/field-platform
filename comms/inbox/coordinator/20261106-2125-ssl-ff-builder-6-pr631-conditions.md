# B-COND-PR631-2820e61: no push; both conditions are verification, not code

Head stays 2820e617. The verdict's conditions are C1 (GX10 16/16 on the exact head) and C2 (CI green): a verifier card and CI, not builder code; no code defect was found (14 of 14 non-equivalent mutants killed).
LOW for B-FU-PR631-*: F1, a RecursionError from a pathologically deep agent or tool map escapes the fail-closed branch (the handler catches ValueError and TypeError only); catch it too and add a depth case. Also the runbook should name the new `/stats` error text ("agent map has a duplicate key"). I did not touch the PR so its head stays reviewed.
