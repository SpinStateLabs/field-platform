VERDICT: C-705 PASS WITH FINDINGS on d5d4fc6d6e75e62a95e8ac68ed97515d455ad30d (PR 358). The new test kills the card's mutant (prefix check removed). The predicate is a text prefix compare, not a URL parse: it rejects every alternative spelling of the same host (safe direction) and accepts dot-segment paths and control characters under the allowed base (harmless at present, see objection 1). UNVERIFIED on any estate; cloud container only.

## Objections first
1. THE PREDICATE IS TEXTUAL, SO PATH SPELLINGS UNDER THE BASE PASS. `is_guarded_killswitch_call` (canary.py:329-334) is `url.startswith(base + "/")` plus a path-prefix check on the remainder. Probe: `<base>/kill/../health` and `<base>/kill/%2e%2e/health` are GUARDED (True), so the operator pair would travel to a route that the docstring (canary.py:323-325) says it never reaches ("never to a read"). `<base>/kill/a b`, a tab and a CR-LF inside the path are also True; http.client refuses such a URL at send time, so no request goes out (not observed here; from http.client's behaviour, general knowledge, MEDIUM). Impact today is nil: every call site builds `{killswitch_url}/kill|revive|drill/{quote(agent, safe="")}` (canary.py:389, 408, 428, 442), and `quote` keeps dots, so an agent id of ".." gives `/kill/..` (a dot segment toward the service root, same host). MEDIUM on the predicate, LOW on impact. Failure conditions: (a) a future caller passes a URL not built from the quoted agent; (b) a proxy or the service normalises dot segments; (c) an agent id of ".." reaches a normalising layer.
2. EVERY ALTERNATIVE SPELLING OF THE SAME HOST IS REJECTED. Observed False for: upper-case scheme or host, a trailing-dot host, an elided default port, the long IPv6 form of the same address, and the same URL with userinfo before the host. For a drill or kill the pair is then NOT attached, the call goes out without it, and the kill-switch (under enforce) refuses; the x3 check reports a failure rather than a silent pass. This is the safe direction. It is also unpinned: mutant G3 (case-insensitive compare) survives the test file. LOW.
3. EMPTY BASE ACCEPTS A BARE PATH. With `killswitch_url == ""` and url `/kill/a` the predicate is True (observed); urllib refuses a relative URL, so no request is sent. The caller reads FIELD_KILLSWITCH_URL from the environment (canary.py:~497-499) and rstrips it; an empty value is not rejected by the predicate. LOW.
4. THE CARD'S TWO MOST DANGEROUS SPELLINGS ARE REJECTED. `http://<base-host>:<base-port>@evil/kill/a` (userinfo trick: urlsplit parses host as evil) is False because the character after the base is "@", not "/"; and `<base>.evil` and a longer port (`80050`) are False. HIGH (observed).

## Steelman
The new test lists the five spellings that matter (other host with the same length, other host, other port, other scheme, base as a prefix of a longer host) and the positive control. The structural reason the predicate is safe is that the path must start at the first character after the base, so the host part of the string is always the base text.

## Probe (script pushed beside this note; 24 URLs and 11 base/URL pairs)
Accepts: the three guarded routes, query, fragment, an empty tail `/kill/`, dot-dot and encoded dot-dot, control characters in the path. Rejects: upper-case scheme and host, trailing-dot host, userinfo variants, `@evil`, longer port, elided port, lookalike suffix, `%2f`, a double slash, a backslash, a bare path. A base ending in `/` or `//` is stripped. HIGH (observed).

## Mutants (19 tests pass unmutated; file restored after each)
| # | Mutant | Result |
|---|---|---|
| G1 | prefix check removed (the card's mutant) | 1 failed |
| G2 | `base` instead of `base + "/"` | SURVIVES: equivalent, the remainder check already needs a slash |
| G3 | case-insensitive host compare | SURVIVES (spelling unpinned) |
| G4 | method compare case-sensitive | SURVIVES (lower-case post unpinned) |
| G5 | method check removed | 1 failed |
| G6 | base not right-stripped | SURVIVES (the call site strips first, canary.py:499; the function's own strip is unpinned) |
| G7 | path check removed | 1 failed |
| G8 | any path guarded | 1 failed |
HIGH (observed).

## Recommended
If the predicate should be strict, parse both sides with `urlsplit`, compare scheme, hostname and port exactly, reject `..`, `%2e`, control characters and userinfo, and compare the normalised path against the three prefixes. Otherwise add three parametrized cases (dot-dot, trailing-slash base, lower-case method) so the current behaviour is pinned.

## What I did NOT do
- No GX10 or estate run; did not send any request.
- Did not check what the kill-switch service does with a dot-segment path (it was not in the card).
- Did not test IDNA or non-ASCII hosts.
