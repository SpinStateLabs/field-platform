# builder-1 S4-11 (lifecycle-manager api persist / findings / operator)
PR: https://github.com/SpinStateLabs/field-platform/pull/659 (draft), head f6afaf52.
Ran: tests/test_persist_and_findings_shapes.py 33 (27 red before, 6 controls); 8 real mutants caught (3, 1, 1, 12, 16, 1, 5, 1 failed); services/lifecycle-manager/tests 302 passed.
Deviation from the card: did NOT use tempfile.mkstemp/NamedTemporaryFile (creates the file 0600, which would silently change last_sweep.json's mode); unique pid+thread+random temp name with a normal write_text instead, and a test pins the mode.
Merge order: #605 and #498 edit the same file in other hunks; not rebased onto them.
Other: #603 (never commented) got its one comment for the main-side lint (fixed on main).
