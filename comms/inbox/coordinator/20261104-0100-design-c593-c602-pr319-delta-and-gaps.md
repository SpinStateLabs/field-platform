# C-593 (delta) and C-602 (spellings still not covered): PR 319 at 34895a4, Lane 10

Reviewed: PR 319 head 34895a4 (`ci/fly-smoke-external-refs-c101`, builder Lane 1; three commits on a9dc4f3: da0e9b4, fedacae, 34895a4; `.github/workflows/ci.yml` one step plus comments, tools/tests/test_ci_external_ref_guard_c101.py +234). My earlier verdict on da0e9b4 was PASS (C-546). One report for both cards, which read the same head. Probe: 20261104-0100-design-c593-c602-grep-samples-probe.py (the shipped pattern is in 20261104-0100-design-c593-c602-pattern.txt, extracted from the workflow by a YAML parse; same flatten as the step).

VERDICT: PASS on 34895a4 (C-593). Every behaviour the card lists holds, nothing in the other jobs changed, 11 own mutants are killed except one equivalent. For C-602: 14 spellings stay uncovered, listed below; one is a coverage REGRESSION chosen on purpose (`data` with spaces around `=`). Confidence HIGH (run); the Actions run on the head is NOT readable here (no GitHub connection): UNVERIFIED, the coordinator's CI read stands.

## ASSUMPTIONS
1. The guard is an accident guard, not an air-gap proof (the PR's own comment says so).
2. "Seven jobs" = the 4-version `tests` matrix plus compose-smoke, fly-image-smoke, compose-upgrade-smoke.

## Objections first (C-602: what the guard can still not see)
1. `data` was loosened in the wrong direction for safety: `data = "https://..."` (spaces around `=`, valid HTML) used to match and now does not, because `data=` is anchored without spaces to stop `data = //` in script text from matching. The comment states it. It trades a false-positive class for a real spelling. LOW-MEDIUM.
2. srcset with a comma and NO space (`srcset="a.png 1x,https://x/b.png 2x"`) is not caught (only `, ` followed by a scheme or `//` counts); HTML allows it. LOW.
3. Still not caught (probe): a leading space inside the quotes (`src=" https://..."`), `background=`, a meta refresh with only `content=`, `<link href="x.invalid/a.css">` (host without a scheme), the HTML-entity scheme `&#104;ttps://`, a backslash scheme, `image-set(`, and every script-side load: dynamic `import()`, `new WebSocket`, `new EventSource`, `sendBeacon`, `XMLHttpRequest.open`, `window.open`, a URL held in a variable then `fetch(u)`. The PR's comment lists most as scope notes. For the script-side loads the real control is the Content-Security-Policy of PR 316 (`connect-src 'self'`), which blocks them in the browser; the grep covers only what the page loads statically. MEDIUM only if PR 316 does not ship. 
4. The guard still inspects ONLY `/`. A second HTML route would be unchecked. LOW.
Steelman: five spellings the old line missed are now caught, with no false hit on my ten safe samples (including `shipping = //`, `mapping=//`, `bigsrc=//`, an `xmlns` attribute and `url(data:)`).

## Results (C-593 checklist)
- Attribute names start a word: `shipping = //x`, `mapping=//x`, `bigsrc=//x` do NOT match; `data-src=//x` and `x-src="https://..."` DO (a hyphen is not alphanumeric, so the prefix counts). HIGH (probe).
- `data` counts only without spaces around `=`: `data="//x"` caught, `data = "..."` not (objection 1).
- srcset: an entry counts when it starts with a scheme or `//`; the first, second (after `, `) and third entries are caught, a relative-only srcset is clean, a newline-separated list is caught after the flatten, a comma without a space is not (objection 2).
- The scope-note comment has no apostrophe, and it sits ABOVE `run:` (a YAML comment outside the block): `shlex.split` of the run block succeeds with 16 lines and 0 apostrophes in comment lines inside it. My mutant that adds an apostrophe to that comment stays GREEN (31 passed): it is EQUIVALENT because the comment is not in the shlex-parsed block; the PR 309 trap applies only to comments inside `run:`.
- Strict YAML (a loader that raises on a duplicate key): parses; four job keys intact (`tests`, `compose-smoke`, `fly-image-smoke`, `compose-upgrade-smoke`).
- Other jobs: compared step by step with the base: `tests`, `compose-smoke` and `compose-upgrade-smoke` have 0 changed steps and equal non-step keys; `fly-image-smoke` has exactly one changed step (index 5, the guard); top-level keys equal. No behaviour change elsewhere. HIGH.
- The step: the page is flattened (`tr '\n' ' '`) so an attribute split across lines is seen; `grep -o -E -i` with `|| rc=$?`; status 0 fails with the error line, status other than 1 fails the step (a broken pattern cannot pass silently, fixing my C-546 finding F-C546-1).
- Shipped console page: no hit, also as a CRLF copy.
- Tests: 31 passed. Mutants of mine, each red: word-start anchor removed (8), `ping` dropped (5), srcset branch dropped (6), `-i` removed (6), flatten removed (7), `data` anchor removed (3), grep status 2 no longer fails (2), `data` allowing spaces (4: the loosening is pinned), fonts branch dropped (4), fetch branch dropped (4); the apostrophe mutant is equivalent (above). 10 of 11 red, 1 equivalent.
- Whole tools suite: NOT run to green here (no full workspace install).
- `fly-image-smoke` SUCCESS on the head: NOT read (no GitHub connection).

## Findings
F-C593-1 LOW-MEDIUM: allow spaces for `data` only when a tag context is present, or add `data[[:space:]]*=[[:space:]]*["']` restricted to a preceding `<object` (a second branch), so the spelling returns without the false hit that motivated the change.
F-C602-1 LOW: add the comma-without-space srcset form (`,[[:space:]]*` instead of `,[[:space:]]+`), `background`, `&#`-encoded scheme and a scheme-less host in `href`/`src` only if the project wants them; each is one token.
F-C602-2 INFO: keep stating in the comment that script-side loads rely on the CSP of PR 316; if that PR is not merged the guard covers less than its name suggests.

## What I did NOT do
Did not read the Actions run or run any workflow. Did not run the whole tools suite. Did not run the builder's mutants. Did not review other pages than `/`. Did not edit the PR.
