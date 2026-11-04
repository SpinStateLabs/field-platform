# Lane O reviewer: PR 365 (C-487 slice 1: field_core.http, one HTTP client constructor, trust_env False) @d570c31dae7cbb9d5a12612951394e6743a3830a. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head d570c31d. Lane A (field-core). Five commits, all with author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>` (git log origin/main..pr365, HIGH). The head does NOT contain current main: 235 commits behind origin/main 97dcfec1; `git merge-tree` onto main: CONFLICT in docs/ENVIRONMENT.md only (HIGH); the source and test files add cleanly. Files: packages/field-core/src/field_core/http.py (new, +136), tests/test_http_client_c487.py (+321), one ENVIRONMENT.md row. I did not write the head. Claimed through dispatch.sh (R-PR365-d570c31).

Objections first: (1) the module is a constructor nothing uses yet: slice 1 adds `client()` and `async_client()`; the existing clients (FieldClient, LedgerClient, RegistryClient, the CLI clients) still read the environment proxy until later slices, and the repo's own allowlist file names them (read of the module docstring, HIGH). The PR protects nothing by itself. (2) the link-local guard on `base_url` applies to LITERAL IP addresses only; a host NAME that resolves to the metadata address passes (probe, run, HIGH: `base_url="http://169.254.169.254.nip.io/"` is accepted; the code comment says "a name, not an address"). A name can resolve anywhere; no DNS is done here. (3) `FIELD_EGRESS_PROXY` may be a plain `http://` proxy, which sends the perimeter header in clear to that hop; the module says this is the operator's explicit choice (docstring, HIGH). (4) the httpx behaviour of `trust_env=False` (SSL_CERT_FILE and SSL_CERT_DIR no longer read when `verify` is default) was read by the author against httpx 0.28.1; I confirmed my environment runs httpx 0.28.1 (run) and did not re-read the httpx source.

Probes (run on the head): timeout 1 accepted; 0, -1, nan, True, None and 3601 each raise ValueError; `base_url` with an IPv4-mapped link-local IPv6 literal is refused.

Run here (cloud, scratch worktree on d570c31d, relative PYTHONPATH): test_http_client_c487.py 124 passed; whole packages/field-core suite 1242 passed, 2 skipped. NOT run: the 16-suite set, CI.

Mutants on field_core/http.py (37 run in a scratch worktree on real code lines; each against the new test file, survivors against the whole field-core suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 trust_env False and follow_redirects False on both constructors | 5 | 5 | 0 |
| B2 timeout is required and bounded: None, zero, negative, nan, bool, over 3600 | 6 | 5 | 1 |
| B3 an httpx.Timeout needs all four parts positive and bounded | 4 | 4 | 0 |
| B4 the pinned keys cannot be passed (each of the eight in turn) | 5 | 5 | 0 |
| B5 verify only True or a context that requires the certificate and the host name | 5 | 5 | 0 |
| B6 base_url: http(s) with a host, no userinfo, no link-local address | 7 | 5 | 2 |
| B7 FIELD_EGRESS_PROXY: http(s) with a host, blank means none, never echoed | 5 | 5 | 0 |
| Total (counted from the rows) | 37 | 34 | 3 |

Survivors (3): 2 equivalent, 1 real LOW pin gap:
- Equivalent (read, MEDIUM): dropping `math.isfinite` from `_positive` (nan fails `0 < nan` and inf fails `<= 3600`, so the other comparisons already refuse both); dropping the `%` zone-id split before `ipaddress.ip_address` (Python 3.9 and later parse a scoped address; the CI matrix is 3.11 to 3.14, so the same result there).
- F-O-pr365-1 LOW: userinfo with a PASSWORD but no username (`http://:secret@host/`) is not pinned: the check `not parts.password` can be dropped and the tests pass; the username-only form is pinned (http.py `_checked_base_url`).

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main, with the ENVIRONMENT.md conflict resolved by `python tools/environment_anchors.py --fix`; I could not run it. C2 none other.
Optional, NEW PR after the head is frozen: F-O-pr365-1 pin; a stated decision on objection 2 (resolve the name at connect time, or document that the guard is for literals only, which the code comment already says in one clause).

Tokens/cost line: not available to me. I do not know.
