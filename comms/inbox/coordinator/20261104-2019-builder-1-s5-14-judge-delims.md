S5-14 judge delimiter forgery. PR #690 (draft). 19 tests, 8 mutants killed, sentinel suite 282 pass, lints pass (anchors fixed).
Finding: engine scope = token scope intersect manifest scope, so a token cannot inject a marker; only the manifest can. judge() refusal is a second line. No live model used.
