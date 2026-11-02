# Builder Lane 1: C-1113 done on a scratch branch, no PR

Branch scratch/c1113-cacert-pins, head e7867e66 (full sha in the push line below), one commit stacked on PR 425 head 186998a7 (main 9addf44f is contained: 425 is built on it). Tests only: services/lifecycle-manager/tests/test_cli_cacert_pins_c1113.py, 4 tests (M14 no default store loaded and exactly one CA in the store; M17 TLS floor >= 1.2; M33 an OSError and a PermissionError are refused by class name with no path or message echoed). No change to cli.py, no push to PR 425 or PR 344, no PR opened: the card gates that on Don's ruling on 344 / Q-09 (Don's F-Q09-1 ruling is given, the landing order of 344, 425 and 381 is not).

Evidence: new file 4 passed. Hand mutants on cli.py `_verify_from`, each run against the new file only: M14 (`load_default_certs()` after the cafile) KILLED; M17 (minimum_version TLSv1) KILLED; M33 (message formats `exc`) KILLED. cli.py restored after each; git status clean.

Not run / not clean, said plainly: the combined run with test_cli_cacert_c1098.py and test_cli_clients_no_proxy_c575.py gave 50 passed, 5 failed; all 5 failures are test_an_ambient_proxy_gets_no_connection_from_the_cli_client[*] with a ConnectTimeout on this Windows host. My commit adds one new file and touches no code, so it cannot cause them, but I did not run them on a separate clean PR 425 checkout. GX10 16-suite run: not run. CI: not read. A GX10 verifier run is requested on this head if the coordinator wants these tests on a PR.

Gates: nothing to reset (no existing PR branch moved).
