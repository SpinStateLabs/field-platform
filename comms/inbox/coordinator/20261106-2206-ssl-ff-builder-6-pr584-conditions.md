# B-COND-PR584-7007f9c: no push; the conditions are CI and GX10

Head stays 7007f9c6. Conditions: CI green (ideally rebased on current main; it is one commit behind, disjoint files) and GX10 16/16 on the exact head: verification only; 13 of 13 mutants killed, no blocking finding.
LOW for B-FU-PR584-*: F1 the test docstring overstates what the bound catches (a value in seconds for 30 days, 2,592,000, is below 999,999,999 and still loads, meaning about 7,000 years; the cap comparison then never refuses): fix the wording, or add a policy ceiling, which is Don's decision (a few thousand days would catch the typo the docstring names). Not touched, so the head stays reviewed.
