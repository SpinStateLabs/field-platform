# restock-needed: verifier (fp-verifier-b)

`dispatch.sh next verifier` returned EMPTY after PR 1011; `level` shows verifier unclaimed=0 RESTOCK (builder 0 RESTOCK, reviewer 5 RESTOCK).
Main is 7a42cb948, which already has a 16/16 report (fp-verifier-c batch m9b @7a42cb9), so no fallback run was started.
Completed by fp-verifier-b since the last restock report: PRs 941, 947, 951 (light), 953, 956, 959, 962, 965, 967, 969, 971, 974, 977, 979, 981, 983, 986, 987, 989, 991, 993, 995, 998, 1004, 1011 and the m5b tools investigation (cause: PR 691). No count went down in any run against its own merge base.
Open points for the coordinator, from my reports: PRs 965 and 991 change defence-shield/agent-incident-retro, which the 16-suite run does not cover (I ran that package separately); several pairs of PRs touch the same files on different merge bases (933/967/974 field-agent and ENVIRONMENT.md, 939/953 spend-governor test_cli_path_segments.py, 993/995 tools/stage1_window.py, 969/971/998 field-core tests, 987/989 conformance-sentinel), so a combined run after landing is not verified.
