# builder Lane O: merge hand-off for my 18 PRs (Don asked "merge"; per the protocol I do not merge, the coordinator does)

Don's instruction in chat: merge, then chose "hand to coordinator". I merged nothing. None of the 18 has the independent reviewer PASS or the GX10 run on its exact head that PROTOCOL requires. Every PR is mergeable=true against main 97dcfec1, and each merges clean with it with 0 wrong environment anchors (checked on the merged result).

CI at last check (heads exact; green CI is not verification):
- all 7 checks green: 491 a86035c1, 496 666b8628, 499 357abe74, 506 f0c3d170; 501 49a11e76 and 508 b3bca137 were 7/7 green earlier (the last read hit a GitHub 502)
- mostly green, rest running: 504 28116b1f, 503 5f38e631, 494 17123ebe, 509 0a0d458b, 515 bd909a51, 516 e5baf6e8, 527 9b21d9ce
- queued: 498 3cbef1b5, 528 1ef80dda, 529 4bb53dfc, 535 02be413f, 536 89d1ab26
- no check has failed on any current head. PR 504 had one failure on tests (3.13) (tools/tests/test_renew_token.py, R.unregistered in the test stack; the same head passed 3.11, 3.12 and 3.14); I re-ran that job once and it is still queued.

NEEDS BEFORE MERGE (all 18): an independent reviewer (not Lane O) and a GX10 run on the exact head.
Extra for some:
- 506 (P-5, money display): a reviewer who checks financial figures.
- 501 (P-19): the mode tests are POSIX-only; run them on POSIX.
- 494, 503, 504: reviewer reads of the older heads still apply to the source (the later commit is a docs-only ENVIRONMENT.md anchor fix); note the new head.
- 500 and 522 (not mine) also edit sealed-ledger api.py, as does my 536; 464 edits federation_broker/cli.py, as does my 501: expect a trivial merge for whichever lands second.
DECISIONS FOR DON (in the PR bodies): 498 sweep bound 3650 days; 503 and 504 numeric-string scores and conforming 0/1 now error; 508 part (b) substring registered-match rule left unchanged; 528 invalid manifest dict is 200 not 422.

Suggested merge order if reviews come in: independent files first, no ordering constraint among them; the sealed-ledger (536) and federation-broker (501) PRs after 500/522/464 if those land first.
