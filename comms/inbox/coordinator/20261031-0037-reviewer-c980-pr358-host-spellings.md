VERDICT: PASS WITH CONDITIONS on 07bd6d634b79ffc1a673fbf596164cfce1b3ddf1

Reviewer Lane 15, cloud-reviewer, C-980, PR 358 (field-agent canary guard; packages/field-agent/src/field_agent/canary.py, its test, and ENVIRONMENT.md cells). Head 07bd6d6 is the head C-43 reviewed (C-965, re-fetched): unchanged. UNVERIFIED: no GX10, CI not read; scratch tree.

## Objections first
1. The guard is a LITERAL text match of the URL against the kill-switch base as written (canary.py:341-355), so every host spelling other than the configured one is "not guarded": it fails closed on the operator pair (the write loses its operator identity), which is the documented direction (reviewer C-705 F-C705-3). The price is availability: a caller whose URL spelling differs from the configured base text by case, a trailing dot, an IPv6 or IPv4 alternative spelling, or a double slash gets no pair and would be refused by an armed operator layer (HIGH, probed).
2. A non-ASCII letter in the agent id (for example an accented letter) and an empty id (`/kill/`) are GUARDED: the check refuses only control characters and spaces, percent signs, backslash, semicolon and dot segments. These are not host problems and not unsafe by themselves (the id is passed on the wire encoded), but nothing in the guard rejects them (HIGH, probed). LOW.
3. The mutant that replaces `url.startswith(base + "/")` by `url.startswith(base)` survives all 189 field-agent tests; it is equivalent: the next test requires the tail to start with one of the guarded prefixes (/kill/, /revive/, /drill/), which a host-lookalike tail never does (HIGH, run and reasoned).

## Host spellings (probe, base "http://kswitch:8005" unless noted)
| URL / base | result |
|---|---|
| exact; method in lower case; query; fragment; trailing slash | guarded |
| base with a trailing slash; base with a path prefix and a matching URL | guarded |
| same host in upper case; trailing dot; other port; longer port with the same prefix (80050); double port; other scheme | not guarded |
| userinfo naming the base then another host (kswitch:8005@evil...); userinfo before the real host | not guarded |
| lookalike suffix (kswitch:8005.evil...) | not guarded |
| double slash before the route | not guarded |
| IPv6 base with the same text | guarded; the same address spelled in full, or a name base with an IPv6 URL, or userinfo after the IPv6 base | not guarded |
| IPv4 base, same text | guarded; an alternative spelling (127.1) | not guarded |
| base spelled in upper case against a lower-case URL | not guarded |
| GET or PUT; path outside /kill, /revive, /drill; /kill without a slash | not guarded |
No host spelling is wrongly ACCEPTED (nothing foreign is guarded); the "wrongly rejected" list is the fail-closed direction above.

## Evidence
189 field-agent tests pass. Mutants on this guard: the host check removed: killed; dot-segment rule off: killed; control-character rule off: killed; query or fragment splitting off: killed; lower-case method check: killed; the slash-append mutant survives and is equivalent (objection 3). Files restored; worktree removed.
Authorship: no-reply Don Hagell identity on every commit. merge-tree with main: 0 conflicts (C-977).

## Conditions
1. Non-blocking: say in the docstring or ENVIRONMENT.md that the pair is withheld for any other spelling of the host, so an armed operator layer refusing a canary write after a config spelling change is not a mystery. 2. Optionally refuse non-ASCII and an empty id in the guard.

Not verified: CI, GX10, real network behaviour of an operator layer refusing an unpaired write.
