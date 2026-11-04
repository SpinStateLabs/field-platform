S5-3 agent-registry scan bad files. PR 679 draft, head d97c534b.
Evidence verified on main. read_scan_file (bounded 1 MiB+1, named ScanInputError for unreadable/oversized/non-UTF-8) used by all five inputs; load_n8n_file also maps invalid JSON and RecursionError. Messages: base name + fixed reason, no bytes.
Tests: test_scan_cli_bad_files.py 19 (16 red before). Mutants 7/7 caught. Suite 330 passed; env-doc + boundary-echo + proxy lint 225 passed; anchors 0 wrong.
Decision for Don: the 1 MiB cap on the n8n file is new; P-2 (scan_n8n_export shapes) touches the same file, trivial merge.
