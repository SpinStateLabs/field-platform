# Reviewer (read-only, post-merge): batch cb3e = MERGE 6, main 198c4df2 -> 3425e23f (PR 356 @cfc08b0, 11 commits)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `3425e23f`** (PR 356 head `cfc08b0fe19b7baa47becf0b86ebfee8e5f34823`). HIGH CARE (SSRF-class host predicate, `field_core/hosts.py`). No earlier file names batch cb3e; this is that file.

## Record checked (HIGH, from git and gh)
- 11 commits 198c4df2..3425e23f (STATUS: 11), 0 nonconforming identities (Don Hagell noreply, author and committer). PR 356 CLOSED with a pointer comment, CI SUCCESS 7/7 on `cfc08b0`.
- Reviewer verdicts naming the head: Q-37 (`20261101-0715-reviewer-q37-q42.md`, `20261101-0905-reviewer-q37-pr356-delta-q28.md`); a verifier A report on the batch head, `20261101-0456-gx10-verifier-A-batch-cb3e.md`, names 3425e23f; the file's own text did not match a "16/16" string in my grep (only the head line matched), so the 16/16 claim in STATUS is not re-verified here (MEDIUM, read the report before relying on it).

## Objections first
1. `is_internal_host` is a deny-by-default predicate on user-controlled text: the way it fails is a spelling the tests did not think of (a boundary of a CIDR, an alias, a suffix check).
2. "Names are trusted by SHAPE and never resolved" (hosts.py docstring): a single-label name or `*.internal`/`*.local` that the resolver sends elsewhere passes when `allow_names` is on; the callers' `allow_names=False` is the control, not this function (stated by the module).
3. The test file is large (390 parametrised cases between the two files) so it kills most mutants; the survivors show where it is only dense, not complete.

## Measured (GX10 ~/ff-work/wt-cb3e at 3425e23f, python -B, own venv)
`test_hosts_c489.py` + `tools/tests/test_internal_host_c489.py`: 390 passed. The 16-suite is the verifier's.

## Mutants (44 rows on hosts.py; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| S1 internal set = loopback, RFC 1918, ::1, fc00::/7 (CIDR boundaries) | 5 | 1 (gap: `192.168.0.0/16` widened to /15, so 192.169.x.x would pass) |
| S2 IPv4-mapped IPv6 follows the v4 address | 4 | 0 |
| S3 canonical dotted quad only | 5 | 0 |
| S4 metadata names are never internal | 4 | 1 (equivalent: with names off the name rule already refuses) |
| S5 names: single label, `.internal`, `.local`, only with allow_names | 4 | 1 (gap: `endswith(("internal","local"))` without the leading dot would accept `foo.evillocal`) |
| S6 `localhost` internal even without names | 3 | 1 (gap: aliases like `ip6-localhost` and `localhost.localdomain` accepted with names off) |
| S7 NUL refused and never raises | 3 | 1 (equivalent: catching ValueError is unreachable behind the fullmatch) |
| S8 `%` only behind an IPv6 address | 3 | 1 (equivalent: a numeric regex that admits `%` still ends at the name rule) |
| S9 non-ASCII never forms a name | 3 | 1 (equivalent: `\d` admits fullwidth digits but the dotted result is refused anyway) |
| S10 an all-digit label is refused as a name | 2 | 1 (my mutant was a no-op: invalid) |
Totals counted from the table: killed 5+4+5+4+4+3+3+3+3+2 = 36; survived 1+0+0+1+1+1+1+1+1+1 = 8; 44 rows. Of the 8 survivors, 5 are equivalent or invalid and 3 are real gaps (S1 192.169.x.x, S5 a suffix without its dot, S6 loopback aliases with names off).

## Conditions
- C1: none blocking (merged; the record is complete; no mutant that makes an external or metadata host internal survived except the three gaps below, each of which needs an input no caller currently sends).
- C2: one follow-up test PR for the 3 gaps: refuse `192.169.0.1` (and `172.32.x`/`11.0.0.1` stay as they are), refuse `foo.evillocal` and `x.notinternal`, and refuse `ip6-localhost` and `localhost.localdomain` with `allow_names=False`.

## Findings (non-blocking; new PR only)
- F-cb3e-1 LOW-MEDIUM: boundary above RFC 1918 192.168/16 is unpinned (192.169.x.x).
- F-cb3e-2 LOW: a dotted name ending in `local` or `internal` without the dot is unpinned.
- F-cb3e-3 LOW: loopback aliases other than `localhost` are unpinned with names off.
- F-cb3e-4 INFO: the verifier A report on the batch head was not confirmed to say 16/16 by my grep.
