VERDICT: PASS WITH CONDITIONS on ab709ed9bf7a2544ca3a253fa055248b43ef684a (UNVERIFIED: cloud reviewer, no GX10, CI not read; the PR's audit test file ran: 172 passed with the pinned acorn)

Same PR and head as the Lane 14 report C-681 and the groomer report C-657 (head re-checked: unchanged). Two commits on main; author and committer are the no-reply identity. Files: services/ops-console/tests/innerhtml_audit.mjs (+314 -?), tests/test_innerhtml_audit_c457.py (+263). This card asks: does it close C-508 F-C508-1..4; shadowed esc and quoted script types still missed; is the shipped page still audited.

OBJECTIONS FIRST
1. The four C-508 findings are CLOSED for the shapes C-508 named, PROVEN by probes through the real audit (small pages with one unsafe sink): quoted and unquoted script types (module, text/javascript, application/javascript, ecmascript, upper case) are now audited; esc shadowed before the real one, as a function, arrow or catch parameter, as a local variable, reassigned later, and called as a method of another object are all reported; a templated onclick and a templated href that can start with javascript: are reported; and the sink list now includes string-key innerHTML, Object.assign, destructuring, insertAdjacentHTML, srcdoc, document.write, createContextualFragment, DOMParser, eval, new Function, setAttribute with an event name or a computed name, outerHTML, URL properties, and a template element's innerHTML.
2. Still MISSED, PROVEN: (a) `window.esc = s => s` (a property assignment) is not seen as rebinding esc; the later `esc(...)` stays trusted. (b) esc used where an HTML escape is not enough: in an unquoted attribute value (`class=${esc(c)}`: a value with a space adds attributes), in a style attribute, in a style element, and in a tag-name or attribute-name position (`<div ${esc(n)}=1>`): all pass as safe. The quoted-attribute and text positions are fine because esc escapes the quote characters and angle brackets. MEDIUM-LOW (the shipped page does none of these, per the C-508 and C-681 reports; the audit would not stop a future edit).
3. Still MISSED, PROVEN: a computed or variable key (`el['inner'+'HTML']`, `el[h] = ...`), Reflect.set and Object.defineProperty on innerHTML, `location.assign`, `window.open`, a data value passed to setTimeout, a jQuery-style `.html()` call, `import()` of data, `new Worker(data)`. Several are not HTML sinks (window.open, import, Worker) but are code or navigation sinks of the same class. LOW-MEDIUM; the header lists some as limits.
4. Not an audit gap but worth naming: static markup with an inline `onclick` or a `javascript:` href and an external `<script src>` are not reported (no template expression, no data). Fine for constants; an external script's content is out of scope. LOW.
5. One probe crashed the audit with a parser exception (a template containing a closing script tag inside a script): it fails loudly rather than passing. LOW.
6. Shipped page still audited: the test file's shipped-page test passes with the pinned acorn (and the earlier reports record that removing esc at any call site turns it red); I did not re-run the per-call-site mutation here. MEDIUM.

ASSUMPTIONS
A1 "Closes" = the named shape is reported on a minimal page. A2 Probes used the PR's own audit function through its test module on pages with the same escape function the tests use; acorn at the pinned version. A3 No mutant run in this card (reported by C-657/C-681).

REASONING
1. Baseline: 172 passed. HIGH.
2. Probe table: F-C508-1 shapes 6 of 6 JavaScript script types flagged, non-JavaScript types (text/babel, importmap, text/plain, ld+json) not audited, which is correct because a browser does not run them. F-C508-2: 8 of 9 shadow forms flagged; window.esc not. F-C508-3: onclick and javascript: href flagged; style, unquoted attribute, style element, tag name, attribute name positions not. F-C508-4: 20 of 31 sink shapes flagged; the misses are in objection 3. HIGH.
3. Diff scan: no estate address, SHA, flag value, deploy status or credential (the test pages are synthetic). HIGH.

CONCLUSION
PASS WITH CONDITIONS. The PR closes F-C508-1..4 as asked and goes well beyond them. The remaining misses are esc used in non-quoted HTML contexts, a window.esc rebind, and indirect or computed sinks. Conditions, none blocking:
- C1 F-C769-1: treat any template expression outside a double- or single-quoted attribute value or element text as unsafe regardless of esc (unquoted attribute, style, tag or attribute name, style element).
- C2 F-C769-2: report `window.esc =`, `globalThis.esc =` and `self.esc =` as rebinding.
- C3 F-C769-3: list the indirect sinks (computed key, Reflect.set, defineProperty, location.assign, window.open, setTimeout of data) in the header as limits or report them.

FINDINGS
F-C769-1 MEDIUM-LOW, services/ops-console/tests/innerhtml_audit.mjs (esc accepted in unquoted attribute, style, style-element and name positions). PROVEN.
F-C769-2 LOW-MEDIUM, same file (window.esc rebind not detected). PROVEN.
F-C769-3 LOW-MEDIUM, same file (computed-key, Reflect.set, defineProperty, location.assign, window.open, setTimeout(data) not reported). PROVEN.
F-C769-4 INFO, same file (an unusual template with a closing script tag crashes the parser step: fails loudly). PROVEN.

NOT VERIFIED: the per-call-site mutation of the shipped page; CI; the browser behaviour of the missed contexts (judged from HTML parsing rules, not run in a browser).
