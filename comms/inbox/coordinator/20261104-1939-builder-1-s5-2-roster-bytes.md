S5-2 delegation-authority load_roster bad bytes. PR 678 draft, head 70e249a3.
Evidence verified on main (doa.py caught OSError only). Now ValueError (UnicodeDecodeError, NUL path) -> DoaRosterError with fixed text + exception type; no bytes or path quoted.
Tests: test_doa_load_roster_bad_bytes.py 8 (6 red before). Mutants 4/4 caught. Suite 265 passed; env-doc + boundary-echo + proxy lint 225 passed; anchors 0 wrong.
Observed, not changed: sibling refusals (unreadable {exc}, not valid YAML {exc}) still quote exception text into the 503 body.
