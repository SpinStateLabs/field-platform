# C-746 cloud read of PR 365 at head 7688aa4 (Lane 9; probes RUN in a scratch venv with httpx 0.28.1 against the module loaded by path; the PR's own tests not run; UNVERIFIED on the GX10)

VERDICT: PASS WITH CONDITIONS. `field_core.http.client` / `async_client` do what the docstring says for the five arguments they pin; the docstring's own contract ("timeout is REQUIRED, None refused") is bypassed by one accepted spelling, and "one constructor" leaves TLS verification and the transport to the caller.

OBJECTIONS FIRST
1. A constructor that exists so no secret-bearing client is built unsafely is only as strong as its pinned list; every un-pinned keyword is a way back to an unsafe client, and call sites will pass kwargs.
2. The card asks about a size cap. The PR has none (the module docstring does not claim one): a caller that wants a bounded response must still build it itself (the FieldClient MAX_RESPONSE_BYTES is separate).
3. A proxy URL is a secret (userinfo). "Never echoed" must hold for every error path, not only the one the PR tests.

ASSUMPTIONS: head 7688aa4 on main 5808a5c (git, HIGH); httpx 0.28.1 as the test pin implies (the PR docstring cites 0.28.1); probes made with made-up values only.

WHAT IT PINS (HIGH, read: packages/field-core/src/field_core/http.py, +77; tests +203)
- `trust_env=False, follow_redirects=False` as literals on the `httpx.Client(` / `httpx.AsyncClient(` call (:63, :70), so the C-57 lint reads them there; `timeout` keyword-only and required; `trust_env`, `follow_redirects`, `proxy`, `proxies`, `mounts` refused if passed (`_PINNED`, :36); the one proxy is `FIELD_EGRESS_PROXY` (http or https URL with a host), refused with a message that does not include it (:39-52). A new ENVIRONMENT.md row documents it.

PROBES (RUN)
1. `client(timeout=httpx.Timeout(None))` is ACCEPTED, as is `Timeout(None, connect=5)` (read, write and pool None): the `isinstance(timeout, httpx.Timeout)` branch (:56-57) passes any Timeout object. The docstring says `None` ("wait forever") is refused; a Timeout whose read/write/pool are None is the same thing. F-C746-1.
2. `client(timeout=5, verify=False)` is ACCEPTED: TLS verification off on a client built to carry the perimeter header. `transport=`, `event_hooks=`, `max_redirects=` and `headers/auth` are accepted too (only `cert="x"` failed, on a missing file). F-C746-2. (`transport` and `event_hooks` can reach the wire or the request before any pin applies; I did not probe what an explicit transport does to the proxy.)
3. Proxy value handling: userinfo accepted and not shown in `repr(client)` or the mounts (both False for a made-up password marker); a path-and-query URL, upper-case scheme and whitespace around the value are accepted (stripped); `http://[::1` and `http://user:pw@` (no host) refused without the value. A proxy with an out-of-range port builds, and a request through it ends in `ConnectError: Connection refused` with no marker in `str(e)` or the full traceback (made-up marker). No leak found on these paths.
4. No size cap anywhere in the module (`limits`, a max response size, a streamed read): `client(timeout=5)` returns an unbounded reader. F-C746-3 (design).

FINDINGS
- F-C746-1 MEDIUM-LOW (PROVEN): an `httpx.Timeout` with any None component is accepted; refuse a Timeout whose connect, read, write or pool is None (or a non-positive number), pin it with a test.
- F-C746-2 MEDIUM-LOW (PROVEN): add `verify` (accept only True, or an ssl.SSLContext the caller built), `transport`, `event_hooks` and `cert` to the refused list, or state in the docstring that the constructor pins five arguments and nothing else; the "one constructor, nothing else can send those headers anywhere" claim needs the pinned list to match. Also the card C-487's later migration will pass the old call sites' kwargs; a call site that passed `verify=` or a transport today would break or bypass.
- F-C746-3 LOW (design): no response size cap (the card's question): decide whether the constructor should offer a bounded read helper, or say the cap is the caller's.
- F-C746-4 LOW (tests): the 14 test names read (test_http_client_c487.py :90-199) pin the five arguments, the timeout rules for None, bools and non-positive numbers, and the proxy value; none passes `Timeout(None)`, `verify=False` or a `transport`.

NOT VERIFIED: the PR's test run, the C-57 lint on this head, any migrated call site (the PR migrates none), behaviour of an explicit `transport` with the egress proxy, httpx versions other than 0.28.1.
CONCLUSION: PASS WITH CONDITIONS: fix F-C746-1 and -2 before the first call site migrates to it; -3 and -4 are optional.
