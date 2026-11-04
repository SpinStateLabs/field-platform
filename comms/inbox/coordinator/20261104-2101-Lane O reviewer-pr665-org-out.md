# LANE O review: PR 665 (attestation-reporter S4-17: org and --out refusals) @ 3dc30026

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head 3dc30026: code+test commit d4ad0c14 and an allowlist-count commit 3dc30026; 0 behind origin/main, 2 ahead, merge clean; both commits Don Hagell numeric noreply. New org.py (+34), api.py +5, cli.py +19/-3 net, tests +132, boundary_echo_allowlist.txt 1 line (`_build::api-reply` 1 -> 2).

Objections first: (1) the tests import `MAX_ORG_CHARS` from the module, so the value 200 that the docstring and the PR title promise is not pinned: `MAX_ORG_CHARS = 199` passes (measured). (2) "Named refusals" is asserted only as a status code or the prefix `refused:`; the API message text and the `--out` message text are not pinned, and the `--out` message is meant to carry the exception type only, but a message that interpolates the OSError text (which holds the server path) passes. (3) The "both texts are built first so nothing is half-written" guarantee is tested with a directory at `board-pack.json`, where the json write fails first either way; a failure in `render_html` is never forced.

Baseline (unmutated, measured): new file passes; attestation-reporter suite 312 passed; tools/tests/test_boundary_echo_lint_c505.py 61 passed. Survivor check against the whole attestation-reporter suite (B7 against the lint test).

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 blank or non-text org refused | 4 | 4 | 0 | 0 |
| B2 limit 200 characters, measured after strip | 5 | 3 | 0 | 2 |
| B3 refuses Cc, Cf, Zl, Zp (reports the position) | 7 | 6 | 0 | 1 |
| B4 returns the stripped name unchanged otherwise | 4 | 3 | 0 | 1 |
| B5 API 422 on /pack and /pack.html, fixed text | 5 | 4 | 0 | 1 |
| B6 CLI: org checked first, --out settled before any query, write failure refused, texts built first | 9 | 6 | 0 | 3 |
| B7 boundary-echo allowlist count for `_build` is 2 | 3 | 0 | 3 | 0 |
| Total | 37 | 26 | 3 | 8 |

Totals counted from the table: 37 = 26+3+8; no invalid, no noapply. B7 is pinned by the existing lint test in tools/tests, not by the new file, as it should be; its three mutants (counts 1, 3, 0) are all killed there.

Survivors, 8, all real gaps (none equivalent):
- B2 `len(org)` (length before strip) and `MAX_ORG_CHARS = 199`: stripped-length and the value 200 unpinned.
- B3 `enumerate(org)`: the reported position includes leading padding; message position unpinned.
- B4 `text.strip().replace("  ", " ")`: inner double spaces are not shown to be kept.
- B5 API detail `"invalid"`: message naming unpinned.
- B6 `--out` message with `({exc})`: OSError text (server path) may be echoed; not pinned. Same for the write-failure message. And the "texts built first" ordering is not pinned.

Conditions: pin the literal 200 (and 201 refused); add a padded 200-character org; add inner double-space and position assertions; assert the exact `--out` message form (exception type only); force a `render_html` failure to pin "nothing half-written". Confidence: HIGH on counts, MEDIUM on gap classification. Token/cost: I do not know.
