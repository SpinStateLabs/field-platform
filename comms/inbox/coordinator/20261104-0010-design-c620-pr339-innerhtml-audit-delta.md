# C-620: delta review of PR 339 (innerHTML audit, second round), Lane 10

Reviewed: PR 339 head 097814d (tests only: services/ops-console/tests/innerhtml_audit.mjs +305, test_innerhtml_audit_c457.py +197), against my C-508 findings F-C508-1..4 and C-576. Probes: 20261104-0010-design-c620-innerhtml-audit-delta-probe.py (23 page shapes) plus my 30 C-508 shapes, 18 tokenizer shapes and 8 mutants of the shipped page, all run through the PR's own audit script with the pinned acorn.

VERDICT: PASS WITH ONE CONDITION on 097814d. It closes all four C-508 findings in the form I stated them, and the shipped page still audits clean (2 scripts, 37 sinks, 0 problems, 0 structure findings). The condition: the script extraction does not follow the HTML tokenizer, so a block closed by `</script >` is not audited at all (proven). Confidence HIGH (run).

## ASSUMPTIONS
1. The audit's job: a later edit that introduces an unescaped sink goes red.
2. The tests need the pinned acorn (8.14.0, integrity hash in the test file); without it they SKIP locally and FAIL under `CI=true`.

## Objections first (failure conditions)
1. Tokenizer differential: a script block ending in `</script >`, `</script\n>`, `</script\t>`, `</script foo>` or `</script/>` is invisible (scripts=0). HTML parsers close the element on all of them. Proof on the shipped page: my mutant that appends a new unescaped `innerHTML` sink to the last block and closes it with `</script >` reports 33 sinks and 0 problems (a normal close reports the new sink as a finding, mutant m5). A mutant that turns the first closing tag into `</script >` drops the script count from 2 to 1 and the sink count to 4, with 0 problems. The test's non-empty-scan assertion (at least 25 sinks) protects the shipped page against a total loss, not against a partial one. HIGH. MEDIUM-LOW impact (a developer must write the odd tag), but this is the evasion class the audit exists for. 
2. Non-literal computed property sinks are still not seen: `el[k] = x` with `k` a variable, and `el['inner' + 'HTML'] = x` (m8: 37 sinks, 0 problems). The PR flags the literal computed key and `Object.assign`, `writeln`, an aliased `document`, `srcdoc`, `createContextualFragment`, `DOMParser`, `setAttribute('on*')`, `eval`, `new Function`. LOW-MEDIUM.
3. `esc()` is an HTML escape; it is correct only in text and quoted attribute values. The audit rejects a template expression inside an inline event handler, at the start of a URL attribute and after `javascript:` (good), but an UNQUOTED attribute (`title=${esc(v)}`) and a `style` attribute with `url(${esc(v)})` pass (probe: 0 findings). The shipped page has neither (grep: 0 templated href/src/action, 0 `style="..${}"`, 0 `url(${`; the 5 `=${` hits are inside JavaScript strings). Future risk. LOW-MEDIUM.
4. Not audited and not reported as a miss: `<script type="text/babel">` (JSX that acorn cannot parse) and an external `<script src>` (the PR 316 CSP blocks external sources at run time). Neither occurs on the page. LOW.
5. If `esc` is renamed, `escChecks` is empty and the audit itself reports 0 problems (mutant m6): the Python test asserts the esc check exists, so the suite goes red, but the .mjs alone does not. LOW.
Steelman: the PR is a large step: it reads every script type, scopes `esc`, rejects templated handlers, adds the integrity pin, and reports structure findings besides per-sink ones.

## Results (finding by finding)
- F-C508-1 (loop and uninitialised variables treated as safe): CLOSED. `for-of` and `for-in` sinks are reported (my probes now green).
- F-C508-2 (name-based `esc` and function resolution): CLOSED as structure findings: a local `esc` (parameter, `const`, catch, class, assignment, update) gives "esc is bound or assigned again ... only the one top-level esc is trusted"; two functions with one name give "function X is defined more than once (the audit keys functions by name)". Both appear in `structure`, not in `sinks[].problems`, so a consumer that reads only `problems` misses them (my first run did): the Python test checks both (151 passed).
- F-C508-3 (sink grammar): CLOSED for the literal forms listed above (my 30 shapes: 7 reds remain: computed key via variable, `setTimeout(<non-literal>)`, and the 4 esc/duplicate cases that are reported under `structure`; the true misses are objection 2 and `setTimeout` of a non-literal).
- F-C508-4 (acorn fetched without integrity): CLOSED: `ACORN_INTEGRITY` is a sha512 pinned in the test file (line 48), the lock is read after install, and a mismatch SKIPS locally and FAILS under CI (my installed acorn of another build mismatched and skipped 151 tests; with the pinned 8.14.0 all 151 pass).
- Shipped page: `scripts 2, sinks 37, problems 0, structure []`, skipped blocks: one `application/json` (not JavaScript). esc encodes the five specials (clean).
- Own mutants on the shipped page: drop one `esc(` (7 findings), `esc` without the single quote (esc check not clean), `esc` renamed (esc check absent: the suite catches it), a function parameter named `esc` (2 structure findings), a new unescaped sink with a normal close (1 finding); the two `</script >` mutants and the concatenated-property mutant are the misses above.
- Tests: 151 passed (pinned acorn); the whole ops-console suite not run to green here (missing dependencies).

## Findings
F-C620-1 MEDIUM-LOW: extract script blocks the way an HTML tokenizer does: close on `</script` followed by whitespace, `/` or `>` (regex `<\/script[\s/>]`), or parse with a real HTML parser; add the five tokenizer shapes and my two mutants as pinned cases. Also fail the audit when the count of `<script` openers differs from the count of extracted blocks plus skipped ones.
F-C620-2 LOW-MEDIUM: flag a computed property assignment whose key is not a literal that is not a safe name (a non-literal key onto an element is a finding).
F-C620-3 LOW-MEDIUM: add an attribute-context rule: a template expression is allowed only inside a double-quoted attribute value or text, never unquoted, never in `style`.
F-C620-4 LOW: make the .mjs fail when `esc` is absent (`escChecks` empty) instead of relying on the Python wrapper.

## What I did NOT do
Did not run the whole ops-console suite or a browser against the page. Did not read the PR's 197 new test lines case by case or run the builder's own mutants. Did not edit the PR.
