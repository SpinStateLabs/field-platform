# C-657 cloud read of PR 339 at head ab709ed (Lane 9; probes RUN in a scratch dir with acorn 8.14.0 (the pinned version) and node 22, plus one Chromium check; UNVERIFIED on the GX10; the PR's own suite not run)

VERDICT: PASS WITH CONDITIONS. The new commit (ab709ed on 097814d) closes the condition Lane 10 raised in C-620 (a block closed by `</script >` was not audited) and adds an opener count that fails on a block it cannot match. One shape in the same family is still hidden: a Unicode space in the end tag.

OBJECTIONS FIRST
1. A static audit decides what is "inside the script" with its own tokenizer; every place that tokenizer disagrees with the browser is a place code can sit unaudited.
2. `\s` in JavaScript regexes is far wider than the HTML whitespace set (tab, LF, FF, CR, space).
3. The opener count catches a `<script` that is swallowed; it cannot catch text that is executed but not extracted.

WHAT THE COMMIT DOES (HIGH, read: innerhtml_audit.mjs:407-421, +13 -2; test file +66)
- Opener `<script(?=[\s/>])`, attributes scanned with quoted-string awareness, end `</script(?=[\s/>])[^>]*>`; so `</script >`, `</script/>` and `</script foo>` end a block.
- `extractionStructure`: the number of `<script` openers must equal extracted plus skipped blocks, else a structure finding (line 0).
- New tests include an opener inside another block, an opener that never closes, a new unescaped sink in a block closed with a space, and the shipped blocks closed with a space (names read at :344-367).

PROBES (RUN, made-up pages only, no value from the repository)
1. Control: a sink after a normal `</script >` close is audited: 1 sink reported (PASS for the C-620 condition).
2. Form-feed between `<script` and the attributes: extracted, the sink reported (PASS).
3. `var t="<!--<script>"; </script>` then a second block with a sink: structure finding "3 openers but 2 blocks extracted" (PASS, the double-escaped case fails loudly).
4. F-C657-1 MEDIUM-LOW (PROVEN, probe 4 plus a browser): `//</script` + U+00A0 + `>` on a line inside a block, followed by `document.body.innerHTML = location.hash;` on the next line. The audit ends the block at the NBSP end tag, extracts one script with 0 sinks and 0 structure findings: the sink is never read. Chromium (Playwright's bundled build) run on the same shape executes the next line (`window.B` set): the browser does not end the script there because its end-tag rule accepts only HTML whitespace. So the audit passes a page whose script runs an unaudited sink. Fix: use `[\t\n\f\r />]` (not `\s`) in both lookaheads, and add a test with U+00A0, U+2028 and U+FEFF in the end tag. (The Python test that "closing the shipped blocks with a space changes nothing", :367, uses an ASCII space.)
5. The shipped page at this head: 2 scripts, 1 skipped, 37 sinks, 0 structure findings: matches C-620's "2 scripts, 37 sinks, 0 problems".

NOT VERIFIED: the PR's Python test suite, its mutant claims, an HTML5-conformant parse (I did not run a full parser against the other end-tag shapes: `</script` followed by `\0`, uppercase, or in `<!--` states beyond probe 3), merge against current main.
CONCLUSION: PASS WITH CONDITIONS: the C-620 condition is closed; F-C657-1 (Unicode whitespace in the end-tag lookahead) is a one-regex fix with a test. This is an audit gap, not a hole in the page (the shipped page is clean).
