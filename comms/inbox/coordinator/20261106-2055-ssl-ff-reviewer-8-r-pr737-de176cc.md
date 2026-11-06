# Review R-PR737-de176cc: PR 737 (lifecycle-manager: pin render_markdown sections, keep registry text on one line, S7-12)
Head reviewed: de176cc86698b334d1b5a4b67c162998e6c0ca15. Behind main; `git merge-tree` against main is clean (tree 3a8a46af).

## VERDICT: PASS

## Checks (HIGH, run by me)
1. Identity: 2 commits (f579ff3d, de176cc8), author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 2 files (engine.py +23/-10, a new test file +146).
2. Code read: `_inline(value)` turns every Cc, Cf, Zl and Zp character into a space, collapses whitespace (`" ".join(text.split())`), and prefixes a backslash when the result starts with `#`, `-`, a backtick, `*`, `>` or `+`. `render_markdown` wraps every registry-, ledger- and manifest-derived string in it: agent_id, owner, reason, status, basis, attested_by, granted_by, scope, the retention and witness detail, `manifest_ref` and the unresolvable reason.
3. Tests on head: test_render_markdown_sections 26 passed.
4. Raw interpolations left in `render_markdown` (my scan of its 62 lines): counters, `days_left`/`days_stale`, config horizons, the `ON/off` word, `token_id[:8]`, the `finding.status` and `witness.status` enums, `witness.estate_watched`, `witness.latest_ts`, `report.swept_at`, `report.method`. These are numbers, constants, enum values or configuration/server timestamps, not caller text; `witness.latest_ts` comes from the ledger event timestamp. I count them as acceptable.
5. Mutants on `_inline` and its call sites, 15 run: 13 killed, 2 equivalent (counted from table).
| # | Mutant | Result |
|---|---|---|
| I1 | drop Zl from the category list | equivalent: `str.split()` already breaks on U+2028 |
| I2 | drop Zp from the category list | equivalent: `str.split()` already breaks on U+2029 |
| I3 | drop Cc | killed |
| I4 | drop Cf | killed |
| I5 | no whitespace collapse | killed |
| I6-I11 | drop the marker `#`, `-`, backtick, `*`, `>`, `+` (one mutant each) | all 6 killed |
| I12 | no backslash escape | killed |
| I13 | agent_id left raw | killed |
| I14 | owner left raw | killed |
| I15 | finding.detail left raw | killed |
6. Probe of `_inline` (inl_probe.py in my scratchpad): `x\n# Forged heading`, CRLF, U+2028, U+2029 and NEL all come out as one line (`x # Forged heading`); a bidi override (U+202E), an ANSI escape byte and a zero-width space become spaces; a leading `#`, `-`, backtick, `*`, `>`, `+`, `---` is backslash-escaped, including after a zero-width space or NBSP; `None` becomes the text `None`.

## Observations (LOW, not conditions)
- Inline markdown still passes through: `[x](http://e)`, `![i](http://e/x.png)` and raw HTML such as `<script>` or `<b>` are kept as typed. Whoever can set an owner or reason text could embed a remote image or link; a previewer that renders and fetches it would make a request from the reader's machine. The PR's stated target is a forged heading or list item (fixed); I did not find the report rendered anywhere in this repository (not searched for a viewer), so the risk is the reader's tool.
- Other block openers are not escaped: `1.` ordered lists, `|` tables, `~~~` fences, `===`, `[`, `<`. In every template the value follows a prefix (`- `, `owner `, `reason `), except `agent_id`, which begins the list item and whose grammar cannot start with a marker, so I could not make one of these form a block; they would matter only if a template put a free-text value first.
- A variation selector in front of a marker (U+FE0F) is not removed (category Mn), and the marker then escapes nothing: `"️# h"` stays as typed; harmless because it does not start the line.

## Not verified
Full lifecycle-manager suite (PR body: 276 passed); how a markdown viewer renders `\#` (the PR says CommonMark renders it literally; I did not render it); GX10 16/16.

## Head frozen at de176cc8.
