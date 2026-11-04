# LANE O review: PR 679 (agent-registry scan: named exit 2 for a bad input file, n8n gets the 1 MiB cap, S5-3) @ d97c534b

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head d97c534b, 1 commit, 0 behind origin/main, Don Hagell numeric noreply. cli.py +2/-5, discover.py +25/-3 (new `read_scan_file`, `load_n8n_file` rewritten), tests +106.

Objections first: (1) the `--api-keys`, `--accounts`, `--secrets-text` and `--principals` inputs already hit `redaction.check_size` downstream, so the new reader's cap is partly redundant for them; a mutant that bypassed `read_scan_file` for `.csv` files still got exit 2 on the oversized case (measured). The cap is genuinely pinned only for the n8n file. (2) The no-echo assertions forbid a marker (`MARK`) and `{not json`, but the marker sits before the bad bytes, so a message that interpolates the decoder error (byte value and position) is not forbidden. (3) "Reads at most 1 MiB + 1 byte, so an oversized file is refused without being loaded" is a resource claim in the docstring; no test observes how much is read.

Baseline (unmutated, measured): agent-registry suite 330 passed. Survivor check ran the whole agent-registry suite.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 a missing, directory or unreadable file is named, not a traceback | 6 | 3 | 0 | 3 |
| B2 the 1 MiB cap: over is refused, exactly 1 MiB passes | 7 | 5 | 0 | 2 |
| B3 a non-UTF-8 file is named, no bytes quoted | 4 | 2 | 0 | 2 |
| B4 malformed or deeply nested n8n JSON is named, content never quoted | 6 | 4 | 0 | 2 |
| B5 the n8n file and the other inputs share one reader | 4 | 2 | 0 | 2 |
| Total | 27 | 16 | 0 | 11 |

Totals counted from the table: 27 = 16+0+11; no invalid, no noapply.

Survivors, 11 = 8 real gaps + 3 equivalent:
Real gaps:
- B1 `except OSError` only: a NUL byte in the path (ValueError, named in the code comment) is unpinned.
- B1 message with the full `{path}` instead of the base name: the test only checks the base name is present.
- B2 message states `MAX_SCAN_BYTES + 1` bytes: the number in the message is unpinned (only "1 MiB" is checked).
- B2 `fh.read()` unbounded: the "refused without being loaded" claim is unpinned.
- B3 `... not UTF-8 text: {exc}`: echoes byte value and position; not forbidden.
- B4 message "not valid JSON" without the file name: the name is unpinned.
- B5 a `.csv` file bypassing the reader: missing, binary or directory `.csv` inputs are unpinned.
- B5 `read_scan_file(p)[:1000000]` silent truncation on the other inputs: unpinned (the exact-1-MiB test uses the n8n file only).
Equivalent:
- B1 and B3 dropping `from None`: changes only the exception chain, not the CLI output.
- B4 `... not valid JSON: {exc}`: a `JSONDecodeError` or `RecursionError` message holds a position or a fixed phrase, not file content (MEDIUM; I did not enumerate every decoder message).

Conditions: add a NUL-path case; assert the whole error line (base name, no directory, no decoder text); add a `.csv` missing and a binary `.csv` case; add a 1,000,001-byte and an exactly-1-MiB case for a non-n8n input; consider a test that monkeypatches `open` to count bytes read. No source defect found. Confidence: HIGH on counts, MEDIUM on gap classification. Token/cost: I do not know.
