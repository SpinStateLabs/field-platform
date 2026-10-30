# C-688: read of PR 331 (sealed-ledger strict anchors parser, order, --min-anchors, BOM) at cdea6de, Lane 10

Read-only; UNVERIFIED on any estate. Probes: 20261104-1000-design-c688-anchors-differential-probe.py (35 file shapes through the old parser and the new `parse_anchors`) and 20261104-1000-design-c688-verify-anchors-probe.py (`verify_anchors` against a real throwaway 5-event ledger), 8 own mutants.

VERDICT: PASS on cdea6de. The new parser differs from the old one in exactly the intended way (a UTF-8 byte order mark); everything else parses or fails identically. `verify_anchors` fails closed on an empty, BOM-only, missing, truncated or garbled file. Two LOW findings (a genesis anchor's hash is never compared; a negative position gives a confusing message). Confidence HIGH (run).

## ASSUMPTIONS
1. The old parser is the expression on main (`raw.decode("utf-8").splitlines()` then `json.loads` per non-blank line).
2. "Different" means one parser accepts what the other rejects, or the reverse, or the record counts differ.

## Objections first
1. `--min-anchors` is a floor the caller must know: removing the NEWEST anchors leaves a valid older prefix that passes every other check (probe: a one-anchor prefix of an honest two-anchor file: ok=True). The PR says so in its docstring and README ("the guarantee depends on this file being the complete, off-box copy"). Without a floor the verifier cannot see a truncation. MEDIUM, stated limit; the CLI default is no floor. `min_anchors=0` through the Python API accepts everything (the CLI rejects below 1). LOW.
2. A position-0 (genesis) anchor is skipped after the order and signature checks (anchors.py:178 `if anchor.chain_length == 0: continue`): its `head_hash` is never compared with `GENESIS_HASH`. Probe: `chain_length: 0` with an arbitrary 64-character hash verifies ok=True. A forged genesis row is harmless information-wise, but a "genesis anchor" that can say anything is not verified. LOW-MEDIUM.
3. A negative `chain_length` fails (good) but with a misleading text: `-1` reports "position -1 (global index -2) is in archived segment None", `-3` reports "out of order after -1" (the initial `previous` is -1). Fail-closed; the message is wrong. LOW. My mutant `previous = 0` instead of -1 survives (18 passed): no test pins the negative case.
4. A string chain_length (`"2"`) is accepted by pydantic coercion and verifies (probe). It is the old behaviour. LOW.
Steelman: one parser used by both the loader and the verifier (they cannot disagree), strict failure on any bad line, a stated order rule (equal positions allowed only with the same hash), and an explicit floor.

## Results (the card's questions)
- Inputs that parse differently from the old parser (35 shapes): 4 differ, all BOM: a file that is only a BOM, a BOM then a newline, a BOM then a record, a BOM then a CRLF record. Old: JSONDecodeError for all four; new: 0, 0, 1 and 1 records. Two BOMs, a BOM at the start of a later line, a U+FEFF inside a string value: unchanged (error, error, ok). UTF-16 (either byte order, with BOM), a stray 0xFF, a latin-1 byte, a NUL byte, a record cut mid-key or mid-value, two records on one line, an array, an unknown or missing field, a float chain_length, U+2028 inside a string (rejected by both because `splitlines` splits on it): identical in both. CRLF, a lone CR, blank and whitespace-only lines, vertical tab and form feed as separators, NEL between records: identical (accepted by both).
- Empty or truncated anchors file: `verify_anchors` on an empty file or a BOM-only file returns ok=False with "holds no anchor records: nothing can be checked" (the C-192 rule kept); a truncated last line raises in `parse_anchors` and verifies as "not a readable anchor file (JSONDecodeError)".
- BOM variants: a single leading UTF-8 BOM is stripped (the intended change); a BOM + an honest record verifies. A double BOM still fails (correct: only one is a BOM).
- Verification behaviour on a real ledger: honest anchors ok; an idle re-anchor (same position and hash) counts once (distinct 2 of 3 records); out of order fails; same position with two hashes fails; a floor of 3 with 2 distinct positions fails; a floor of 2 with one position repeated fails (counts once); a chain length beyond the chain fails ("history erased"); an upper-case or space-suffixed hash fails (compared exactly).
- Tests: 18 passed (test_anchors_c573.py). Mutants of mine, each red unless noted: order check `<` to `<=` (3 failed), order check removed (1), same-position check removed (6), floor off by one (1), floor counts records not positions (1), BOM strip removed (2), BOM strip removes two characters (1); SURVIVOR `previous = 0` (objection 3). 7 of 8.
- Whole sealed-ledger suite: not run to green here.

## Findings
F-C688-1 LOW-MEDIUM: compare a genesis anchor's `head_hash` with `GENESIS_HASH` (replace `continue` by the check) and pin it with a forged-genesis case.
F-C688-2 LOW: reject a negative `chain_length` in `AnchorRecord` (`ge=0`) so the message is "invalid record" and pin it; make `min_anchors` below 1 an error in the API as in the CLI.
F-C688-3 INFO: make the "complete off-box copy" assumption visible in `ledger verify` output when no floor is given.

## What I did NOT do
Did not run the whole sealed-ledger suite or the witness path. Did not test signed anchors with a real key (not needed for the parser). Did not edit the PR.
