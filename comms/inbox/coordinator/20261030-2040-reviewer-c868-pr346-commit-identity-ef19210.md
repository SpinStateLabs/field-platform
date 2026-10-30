VERDICT: PASS WITH CONDITIONS on ef19210e309ef20bfe47924493ff22e21de02e3a  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-868, PR 346 (commit-identity guard) against Lane 14's C-788 (PASS WITH CONDITIONS on e4e9898). The head moved one commit: ef19210 ("the identity guard folds two more full stops; the job fails on a range of no commits"), +70 -6 over four files. All probes used synthetic values on a reserved `.invalid` domain; no real address is in this report. This SHA only.

OBJECTIONS FIRST
1. C-788 conditions: F-C788-1 (ideographic full stop and half-width ideographic stop do not fold to ".") is CLOSED: tools/check_commit_identity.py `_DOTS` translates U+3002 and U+FF61 after NFKC; probe: `name @ domain<U+3002>invalid` and `<U+FF61>` forms are now flagged; mutants removing either entry, or all, go red. F-C788-2 (a range with zero commits exits 0) is CLOSED for CI: `--require-commits` exits 2 on an empty range, and the CI job passes the flag in both branches (ci.yml, the two `python3 tools/check_commit_identity.py --require-commits ...` lines). Probe in a temporary repository: empty range without the flag exit 0; with the flag exit 2 with a message; one commit exit 0; non-existent base exit 2; a commit whose name and email are address-shaped exit 1 with only the SHA prefix and the FIELD names printed (no value). Confidence HIGH.
2. F-C788-3 (trailers are not read: an address in Co-authored-by or Signed-off-by passes) is OPEN and stated in the docstring and the CI comment; it is the one remaining leak path of the class. F-C788-4 (the allowed-domain variable can appear in the public job log) is OPEN, now stated in the CI comment ("a repository variable, not a secret: its value can appear in this public job log"). Confidence HIGH.
3. Spellings of an address-as-name still missed in the SPACED-domain form (`word @ domain<X>invalid`, probe with synthetic values): the Arabic full stop (U+06D4), the middle dot (U+00B7), the bullet (U+2022) and the katakana middle dot (U+30FB) pass; spelled-out "at ... dot ...", a Cyrillic homoglyph for the letter a in "at", a double-encoded at-sign (%2540) and a text escape (@) pass. The docstring declares spelled-out and homoglyph forms out of scope; it does not list these four dot-like characters or double encoding. Flagged: plain, full-width at and full stop, small at and full stop, one-dot leader, [at], (at), %40, &#64;, &#x40;, a line separator, tab, RTL override, variation selector and combining mark. LOW: each needs deliberate writing and the name rule is a safety net, the email rule being the main one.
4. Legitimate commits the guard would block (false positives, by design or not): an unconfigured identity (`unknown@unknown`, `none@none`), a machine-derived `root@host.local`, a GitHub Enterprise Server no-reply host, an upper-case local part `NOREPLY@anthropic.com` or `NoReply@github.com` (the local part is case-exact; GitHub writes lower case), a no-reply local part with a dot, an email in angle brackets or quotes (git stores neither), a name holding an at-sign between two words with no spaces (`a@b`: documented accepted false positive). Legitimate commits that PASS: a numeric-id plus handle no-reply (also upper-case domain and mixed-case handle), a handle no-reply, `noreply@github.com`, `noreply@anthropic.com`, `[bot]` accounts and Copilot-style ids, names such as `dependabot[bot]`, `look [at] this`, `Sam at the office`, `J. R. Smith`, a lone `@handle`. HIGH on the probe; whether a given estate commit exists in a false-positive shape: not in source.
5. Over-acceptance in the email rule: a `<handle>@users.noreply.github.com` of any length passes (a 40-character handle, 5,000 characters), although GitHub handles are at most 39; a handle ending in a hyphen or with doubled hyphens passes; a bare number `123@users.noreply...` passes. No personal mailbox can sit under that domain, so this over-acceptance does not leak an address. LOW/INFO.
6. Performance: 20,000- and 200,000-character names and emails (many repeats of the shapes the patterns use) returned immediately; no catastrophic backtracking seen. HIGH on the inputs tried.
7. Allowed domain (`--allow-domain`): exact domain passes; a subdomain, a suffix lookalike and a userinfo trick are refused. HIGH.

ASSUMPTIONS
A1 Card scope: each C-788 condition at file:line, spellings the guard misses, no address printed. A2 The name rule is a net, not the primary control.

REASONING / CHECKS
- Tests: tools/tests/test_check_commit_identity_c564.py and test_ci_commit_identity_job_c564.py: 219 passed.
- Mutants on check_commit_identity.py (each restored, nothing committed): dot map without U+3002 KILLED; without U+FF61 KILLED; map empty KILLED; `--require-commits` branch disabled KILLED; its exit code changed to 1 KILLED; NFKC replaced by NFC KILLED; format-character stripping disabled KILLED; domain case-insensitivity removed KILLED. Eight of eight. A ninth mutant I wrote against ci.yml did not apply (text mismatch): the CI flag is covered by the job test file, which I did not mutate.
- Commit identity: 7 commits on the branch (fb9dc61, 6e4a9d1, a150b6c, afb25af, c669ea6, e4e9898, ef19210); author and committer Don Hagell no-reply on all. Diff: no address, flag value, credential or deploy status (the workflow reads the allowed domain from a repository variable, never in the file).

CONDITIONS
C1 (non-blocking) List the four dot-like characters and double encoding as known misses in the docstring, or fold them.
C2 (non-blocking, carried) F-C788-3 trailers; F-C788-4 the public log line for the allowed domain.
C3 (non-blocking) Decide whether upper-case no-reply local parts should pass (GitHub writes lower case; a hand-set identity may not).

NOT VERIFIED
GX10 full set, CI by run id (the job's real behaviour on a pull request), the ci.yml flag by mutant, the whole tools suite, direct pushes and squash-merge identities (out of the guard's reach, stated).

CONCLUSION
Both C-788 conditions that Lane 14 asked to close are closed at ef19210 and pinned (8 of 8 mutants die). Open items are the trailer path, the public-log note and a few unfolded dot characters. PASS WITH CONDITIONS, UNVERIFIED.
