# Review PR 836 @fade1092 (G16: phase_g_stage0_check; delta over my PASS WITH CONDITIONS on 989f14b7) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `fade109239acfda3ed2756e1ddf840080bbf798d`. My condition C1 (pin the eight services and their literal proxy paths) is met, and the optional LOWs I listed were also taken. Remaining: the standard CI on the head (my C2).

## Checks (HIGH, run by me)
- Delta 989f14b7..fade1092: 3 files; tools/phase_g_stage0_check.py changes one docstring line ("every FIELD_OPERATOR_* flag is blank" -> "every operator flag behaves off"), the deploy-record template reword, and 82 added test lines. No logic change in the tool.
- Identity: 2 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files.
- The pin: the test file now carries `LITERAL`, the eight (path, service) pairs written out, and the fake estate serves from that table, not from the tool's. `test_the_tool_checks_exactly_the_eight_services_at_their_literal_proxy_paths` compares the tool's table to it and counts eight distinct labels; a run requests each of the eight paths once; each service stopped, and each service answering as another name, fails the whole check with the right line (parametrised over all eight). The literal paths match the Caddyfile routes I verified in the first review (seven prefixes plus the console at the root).
- Boundaries now pinned: a non-200 answer fails even with a healthy-looking body (HTTP 503 case); `identity_present` missing fails closed; an empty-string identity id counts as blank; a full build id never prints, whether the check passes or fails, with or without `--expect-build-sha`.
- Wording: the template and tool now say "behaves off" and "cannot prove a variable is unset" (a test pins both phrases and the absence of "unset in every" and "is blank, seen from").
- Tests on the exact head (Windows): test_phase_g_stage0_check_g16.py 39 passed (was 16); `environment_anchors --check` 0 wrong rows.

## Mutants (the same 23 as in my first review, re-run on this head; counted from the table)
| group | mutants | killed | survived |
|---|---|---|---|
| flags A1-A7 | 7 | 7 | 0 (A5 and A7 now killed) |
| service and sha B1-B9 | 9 | 8 | 1 (B7) |
| exits and calls C1-C5 | 5 | 3 | 2 (C1, C2) |
| list D1-D2 | 2 | 2 | 0 (D1 and D2 now killed) |
Totals: 23 mutants, 20 killed, 3 survived (7+9+5+2 = 23; 7+8+3+2 = 20; 0+1+2+0 = 3). Was 15 of 23. The three survivors are the same ones I judged equivalent in the first review: C1 (`Estate(base, None)` sends no credential whatever the flag says), C2 (an empty result cannot occur: every service adds a check), B7 (each missing service already fails its own check).

## Not verified
CI/GX10; Linux; a real estate (the evidence is code reading and the fake-estate tests).
