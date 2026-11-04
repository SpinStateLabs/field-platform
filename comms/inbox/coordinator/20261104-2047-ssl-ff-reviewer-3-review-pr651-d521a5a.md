# Review PR 651 @ d521a5a8c0d437b3aca16ba469e05e5626ef9bf4 (delegation-authority CLI: unreachable is one line, non-JSON errors are a status line) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head d521a5a8. UNVERIFIED (cloud, no GX10). Condition 1 pins the operator-identity pass-through that this refactor routes through a new helper.

## Objections first
1. Every call now goes through `_request(..., pair=pair)`. If a verb drops `pair`, the write goes out with no operator identity and is refused under ENFORCE, with no test noticing. Probed (R9, R10): both survive the whole suite.
2. `_q` is claimed to keep `/`, `?`, `#`, `%` in an id from changing the route. `%` is unpinned (Q5), and dot segments are not covered at all (measured below).
3. `introspect` and `oauth-introspect` still echo `resp.text` of a 200 BEFORE `_active` rejects a non-object body; the PR's "never echo the body" covers `_fail` only (read from the diff; not changed here).

## Facts (HIGH)
- Head fetched via refs/pull/651/head = d521a5a8; 2 commits (the CLI change; an ENVIRONMENT.md anchor refresh); contains current main; author AND committer on both: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 3 files, +217 -24: `delegation_authority/cli.py` (`_fail`, `_q`, `_request`, `_active`, five verbs), `docs/ENVIRONMENT.md` (anchors), `tests/test_cli_verbs.py` (+165).
- Baselines unmutated: `test_cli_verbs.py` 51 passed; whole delegation-authority suite 308 passed.
- Measured with `httpx.URL` on the head: `_q("..")` is `..` and the request goes to `/revoke`; `_q(".")` goes to `/tokens/revoke`. For `a/b` the wire path is `/tokens/a%2Fb/revoke` but `request.url.path` (decoded) is `/tokens/a/b/revoke`, which `is_guarded` rejects (False), so such an id is sent WITHOUT the operator pair.

## Mutants (new test file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| `_fail`: one status line for a non-object body, no echo, exit 1, detail kept for an object (F1-F5) | 5 | 5 | 0 |
| `_q`: `/`, `?`, `#` quoted and applied to revoke (Q1-Q4) | 4 | 4 | 0 |
| `_q`: `%` quoted (Q5) | 1 | 0 | 1 |
| unreachable: exit 2, class name only, to stderr, nothing-was tail, HTTPError family (R1, R3-R8) | 7 | 7 | 0 |
| the operator pair reaches mint and revoke (R9, R10) | 2 | 0 | 2 |
| `_active`: fails closed for a non-object 200, boolean only, missing key, stderr, used by both verbs (A1-A6) | 6 | 6 | 0 |
Totals counted from the table: 5+4+1+7+2+6 = 25 valid rows; killed 5+4+0+7+0+6 = 22; survived 3 (Q5, R9, R10); 1 more edit (R2) did not anchor and is not counted.

## Survivors and findings
- F-R651-1 MEDIUM (R9, R10): no test shows that `mint` and `revoke` send the operator pair after the refactor. Pin one request header check per guarded verb (`x-field-operator`, key present on mint and revoke, absent on introspect and list).
- F-R651-2 LOW-MEDIUM (Q5): `%` in an id is unpinned; with `%` left unquoted, `a%2Fb` reaches the wire as `/tokens/a%2Fb/revoke` and the server decodes it, so one id spans two segments on the server side.
- F-R651-3 LOW-MEDIUM (measured): dot segments are not handled by `_q`: `revoke ..` goes to `/revoke` and `revoke .` to `/tokens/revoke`. They fail closed here (unrouted), and the operator typed them, but the docstring "never change the route" is false for them; the other clients in the repo refuse dot segments (field-agent C-98). Refuse `.` and `..` in `_q`.
- F-R651-4 LOW (measured): an id containing `/` is sent without the operator pair because the guard judges the decoded path; it fails closed (the receiver refuses) but with a misleading error. Interplay of `_q` with `is_guarded`.
- F-R651-5 LOW: a 200 non-object body is still echoed by `typer.echo(resp.text)` before `_active` fails closed (read from the diff).

## Conditions
1. Pin F-R651-1 (and ideally F-R651-2, F-R651-3) before this lands, or the coordinator rules them follow-ups.
2. GX10 16/16 and CI on this head rebased on current main.
