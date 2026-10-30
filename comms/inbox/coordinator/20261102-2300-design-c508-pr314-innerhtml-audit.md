# C-508: review of PR 314 (innerHTML audit), Lane 10

Reviewed: PR 314 head f4bbff1 (`test/console-innerhtml-esc-c457`; services/ops-console/tests/innerhtml_audit.mjs and test_innerhtml_audit_c457.py; tests only). This is item 4 of my note 20261101-0210 section 3. Probe: 20261102-2300-design-c508-innerhtml-audit-probe.py (30 tiny pages run through the PR's own audit script; `acorn` at /opt/node-tools here).

VERDICT: PASS WITH CONDITIONS on f4bbff1. On the shipped page the audit is sound and proven: 2 inline scripts, 32 sinks, 0 findings, `esc` encodes the five specials; every mutant I ran went red. The audit can be fooled by shapes the page does not use today; two are one-line fixes.

## ASSUMPTIONS
1. The goal is: a later edit that introduces an unescaped sink goes red.
2. Acorn at /opt/node-tools is the pinned 8.14.0 (not verified; version of the install not read).

## Objections first (failure conditions: where the audit says "clean" and is wrong)
1. Unsound rule: a variable declared WITHOUT an initializer is treated as safe. `resolveIdent` finds the declaration (`declaredIn`) and returns the findings of its assignments; a `for (const r of rows)` or `for (const k in data)` variable has none, so it returns "no problem". Probe: `let out=''; for (const r of rows) { out += r; } el.innerHTML = out;` comes back CLEAN (miss, 2 cases: for-of and for-in). This is the most realistic regression (rendering a list in a loop). HIGH (run).
2. Name-based resolution: `esc(...)` is safe by NAME at any scope, so `function f(esc){... esc(x)}` or `const esc = s => s` inside a function is trusted (miss, 2 cases); and `functions` is a Map by name, last definition wins, so an unsafe function of the same name as a safe one in another scope is never audited (miss: two same-name `row` functions, the top-level unsafe one unseen). The `esc` check itself runs on the last definition only. HIGH (run).
3. Sink grammar is four shapes (`innerHTML`/`outerHTML` assignment, `insertAdjacentHTML`, `document.write`). Not recognised, so never audited (all miss, sinks=0): a computed member (`el['innerHTML'] = x`, `el[k] = x`), `Object.assign(el, {innerHTML: x})`, `document.writeln`, an aliased document (`const d = document; d.write(x)`), `srcdoc`, `createContextualFragment`, `DOMParser` then insertion, `setAttribute('on...', x)`, `a.href = x` (a `javascript:` URL), `eval`, `new Function`, `setTimeout(string)`. HIGH that the audit misses them (run, 11 cases). None occurs in console.html (grep for each token returned nothing), so this is a future-regression gap.
4. Static scope only: inline event-handler attributes (`onclick="saveOperator()"` and the like) are script the audit never parses; the policy added by PR 316 keeps `script-src 'unsafe-inline'`, so they run. LOW-MEDIUM.
5. The test downloads acorn from npm at run time (`npm install acorn@8.14.0`, no lockfile or integrity pin, test_innerhtml_audit_c457.py fixture). A registry or mirror compromise would run attacker code in the test process. With `CI=true` an unavailable install is a FAILURE (good: the gate cannot vanish), with a missing node/npm outside CI it is a skip. LOW-MEDIUM. HIGH (code read).
Steelman: the audit is a regression alarm for the page's own idiom (template literal, `esc(...)`, `.map().join()`), not a taint tracker; it parsed 32 real sinks through the page's own helpers and found none, and it is strictly better than the previous grep.

## Results (card's questions)
- 54 tests passed on the head (HIGH, run, `PYTHONPATH` to the console and core sources; with no path the file fails to collect: environment, not the PR).
- The shipped page: scripts 2, sinks 32, findings 0, `esc` output `&lt;img src=x onerror=&quot;a&quot;&gt;&#39;&amp;` clean.
- Template literal, concatenation, `+=`, helper return, `map().join`, conditional, `||`, catch parameter, destructured parameter, `await`, `arguments`, `this.v`, an `innerHTML` read-modify, `.toString()` on data: all REPORTED (probe green). `esc`, `Number(...)`, a template of `esc` pass as controls.
- Own mutants on the shipped page, each red: drop one `esc(` at a template site (7 findings, because that helper feeds several sinks); `esc` without the single quote (esc check not clean); `esc` encoding nothing (not clean); a new unescaped sink appended (1 finding). Control (unmodified): 0 findings.
- Empty scan: a page with no script gives `scripts: 0, sinks: []` from the node script; whether the Python side turns that into a failure I did not read (the grep for it printed nothing above): UNVERIFIED, check `test_innerhtml_audit_c457.py` for a non-empty assertion.
- The whole ops-console suite: NOT run to green here (4 collection errors from missing dependencies); the 54 audit tests were.

## Findings and fixes
F-C508-1 MEDIUM-LOW: treat a declaration without an initializer as a finding in `resolveIdent` (one line: when `assignmentsTo` is empty return `problem(id, ...)`). I applied it to a copy: the shipped page still has 0 findings, so the fix costs nothing today. Pin: the for-of and for-in cases.
F-C508-2 LOW-MEDIUM: resolve `esc` by scope (only the page-level `esc`; a local binding named `esc` is a finding) and key functions by node, not name (audit every definition of a name, or fail on a duplicate name). Pin: the three shadow cases.
F-C508-3 LOW: instead of extending the AST rules, add a plain test that the page contains none of the escape-hatch tokens (`['innerHTML']`, `writeln`, `srcdoc`, `createContextualFragment`, `setAttribute("on`, `eval(`, `new Function`, `Object.assign(` onto an element); a list that the page satisfies today and that makes any new use a conscious edit.
F-C508-4 LOW-MEDIUM: vendor acorn (one file) or pin the install by lockfile and integrity; the PR 316 CSP and this audit assume the test environment is trusted.
F-C508-5 INFO: confirm the non-empty-scan assertion (see above).

## What I did NOT do
Did not run the whole ops-console suite. Did not read the builder's 54 tests case by case or run the builder's stated mutants (ran my own four). Did not audit inline event-handler attributes (objection 4). Did not check the installed acorn version. Did not edit the PR.
