# C-546: review of PR 319 (CI external-reference guard), Lane 10

Reviewed: PR 319 head da0e9b4 (`ci/fly-smoke-external-refs-c101`; `.github/workflows/ci.yml` one grep line plus a YAML comment, new tools/tests/test_ci_external_ref_guard_c101.py; one commit on a9dc4f3, main now b929f12). Probe: 20261103-0100-design-c546-grep-samples-probe.py (extracts the shipped pattern from the workflow with a YAML parse, then `grep -n -E -i` on 17 must-catch, 19 beyond-the-list and 5 safe samples; it expects `pattern.txt` next to it, written by its first step: see the note at the end).

VERDICT: PASS on da0e9b4. The guard does what the PR says, nothing in the workflow structure broke, and the PR's own comment ("an accident guard, not a proof of an air gap; review is") is honest. Findings LOW. Confidence HIGH (run) except CI status (not readable).

## ASSUMPTIONS
1. "Seven jobs" means the 4-version `tests` matrix plus compose-smoke, fly-image-smoke and compose-upgrade-smoke (the file has 4 job keys: `tests`, `compose-smoke`, `fly-image-smoke`, `compose-upgrade-smoke`).
2. The guard runs against the page served at `/` by the console, saved to `$RUNNER_TEMP/root.html`.

## Objections first (what the guard cannot see)
1. It is a line-oriented regex over HTML text. Not caught (probe, 14 of 19 shapes beyond the PR's list): `srcset`, `imagesrcset`, `ping`, an attribute split across two lines (`src=\n"https://..."`), `new WebSocket("wss://...")`, `new EventSource`, `XHR.open`, `navigator.sendBeacon`, `importScripts`, dynamic `import("https://...")`, `window.open`, a URL held in a variable then `fetch(u)`, an HTML-entity-encoded scheme (`&#104;ttps://`), `image-set(`. Caught beyond the list: `formaction`, `xlink:href`, `location.href = "https://..."`, `<base href>`. For the guard's stated purpose (customer perimeters are air-gapped) most uncaught shapes are network CALLS from script, which the Content-Security-Policy of PR 316 (`connect-src 'self'`) blocks at run time in the browser; the grep covers what a page LOADS. So the two are complementary only if PR 316 ships. MEDIUM.
2. Pattern at risk of vacuous pass: the guard is `if grep ...; then error; fi`. If the pattern stopped compiling, grep returns 2, the `if` sees "false", and the step PASSES. The tests exercise real matches (17 pass), so a broken pattern would fail them, but the workflow step itself does not distinguish exit 1 from 2. LOW.
3. A guard on one page: only `/` is checked; the console's other static content is inline, so this is currently complete for the console (grep of the shipped page: no hit), but a second HTML route would not be covered. LOW.
Steelman: five real shapes the old line missed are now caught (single-quoted and unquoted attributes, `poster`/`data`, a meta refresh, a spaced `url(`, `fetch(`), with `-i`; no false positive on the safe samples.

## Results (the card's questions)
- Workflow valid: parsed with a strict loader that raises on a duplicate key: no error; the four job keys intact.
- The shipped grep (flags `-n -E -i` and the pattern, extracted from the YAML, length 240): all 17 must-catch samples caught, including uppercase (`<IMG SRC="HTTPS://...">`, `HTTP-EQUIV=REFRESH`), spaces around `=`, `poster`, `data`, `action`, a spaced and single-quoted `url(`, `@import`, a template-literal `fetch`, the font hosts; a double-quoted control still matches.
- The console page itself yields NO hit (`grep` exit 1) on the PR's tree.
- Backtracking: `grep -E` uses an automaton; a 1.6 MB line of `src ` repeated and a 300,000-space `url(` line each finished in under 15 ms. No pathological case found.
- False positives on safe text: none (plain URL in prose, a `data:` icon, a relative `src`, a `//` comment, `url(data:...)`).
- Tests: 17 passed (the card says 16). My own mutants, each turned red: drop `poster` (5 failed), drop `http-equiv` (4), break the `url(` branch (2), remove `-i` (2), drop `@import` (2), drop the font hosts (4). The builder's 13 mutants were not re-run.
- Whole tools suite: NOT run to green here (no full workspace install in this container).
- The Actions run on the head: NOT readable (no GitHub connection in this session): UNVERIFIED; the coordinator's CI check stands.

## Findings
F-C546-1 LOW: make the step distinguish "no hit" from "grep error": `grep ...; rc=$?; [ $rc -eq 1 ] || { echo ...; exit 1; }` (rc 0 = hit, rc 2 = broken). One line, no behaviour change on the shipped page.
F-C546-2 LOW: add `srcset|imagesrcset|ping|formaction` to the attribute list (a one-token change per name, all attributes that load or send to a URL) and a multi-line pass (`tr '\n' ' '` before the grep) so an attribute split across lines is seen; both are cheap and the PR's own comment already frames the guard as best effort.
F-C546-3 INFO: the PR text says 16 tests; the file has 17.

## What I did NOT do
Did not read the Actions run (no connection) or run `tools/` whole-suite. Did not re-run the builder's 13 mutants (ran six of my own). Did not test any other CI job's behaviour. Did not edit the PR. Note: the probe script reads `pattern.txt` that I produced by extracting the pattern from `.github/workflows/ci.yml` of the PR head; to reproduce, extract it the same way (the one `grep -n -E -i` line of the console-page step).
