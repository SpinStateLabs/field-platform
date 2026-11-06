# B-COND-PR750-6bdbb4c (ssl-ff-builder-8)
Applied the reviewer's MEDIUM and two LOWs on the PR branch scout-s7-25-export, new head a5330d3a6239e3ca3b6607d31d11ade7caaeb888 (tests only, api.py untouched):
- finding 1+2 (M12b, M12): the ValueError branch test now asserts the log carries "export failed: ValueError" and not the stored text.
- finding 3 (M17): new test pins MAX_OUT_DIR == 4096 literally.
Local run (PYTHONUTF8=1, services/sealed-ledger): test_export_route_failures.py 14 passed. Mutants re-run: M12 killed, M12b killed, M17 killed.
Branch base is still the stale ebb027a2 (reviewer: merge-tree clean against main). Re-review needed on the new head.
