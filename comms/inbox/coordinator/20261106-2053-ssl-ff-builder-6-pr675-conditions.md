# B-COND-PR675-5f0db83: conditions pushed on PR 675, new head 9f150a56a1ba

Tests only (no source change) in test_parse_instant_and_require_https.py: non-string bounds (int, float, bytes, list, object) are InvalidTimeBound; the whole parse_bound message pinned with a note that the echo of the caller's own filter value is intended; mixed-case URL path and HTTPS:// scheme keep their case; naive timestamp is UTC under TZ=America/New_York (skipped on Windows: no time.tzset; it runs in CI on Linux, so not verified by me).
Mutants: ValueError-only catch, echo dropped, lower-cased URL killed (3 of 3); strip-both-ends is equivalent (leading slash already refused). 34 passed, 1 skipped locally (PYTHONUTF8=1, Windows). Identity Don Hagell both fields. Open: CI, re-review.
