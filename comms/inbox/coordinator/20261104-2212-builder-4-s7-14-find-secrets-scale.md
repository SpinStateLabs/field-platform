S7-14 -> https://github.com/SpinStateLabs/field-platform/pull/744
HIGH: MEASURED 20k hits 17.7s/31.3s -> 0.27s/0.47s; 41k -> 0.5s/1.0s. Output byte-identical vs old algorithm (oracle, 200 random + corpus). 3/3 mutants red. OPEN QUESTION for Don: cap hits per scan with a truncation flag (not done).
