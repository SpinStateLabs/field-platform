# builder Lane 12: Q-121 conditions on PR 475 (C-1190), head 19d14a49054393b5763a234c69f0ec71fa4147a0 NOT touched (head-freeze)

Lane 15's two findings (F-Q121-1, F-Q121-2) are correct (HIGH, read against tools/renew_token.py:312-332). I did not push. The fix is one paragraph in docs/runbooks/token-renewal.md (lines 206-212 on the head). For the batch rebuild, replace

  "one named by `FIELD_OPERATOR_KEY_FILE` that is unusable prints `warning: ...; no operator identity is sent` and the run carries no identity, UNLESS an operator flag is also given (`--operator-id` or `--operator-key-file`): then it is refused (exit 2, `--operator-key-file is <problem>; nothing sent`, the flag name appears even though the file came from the variable)."

with

  "one named by `FIELD_OPERATOR_KEY_FILE` is read only when an operator id is present (`--operator-id` or `FIELD_OPERATOR`) and no `--operator-key-file` is given. If it is unusable and the id came from `FIELD_OPERATOR` alone, it prints `warning: FIELD_OPERATOR_KEY_FILE is <problem>; no operator identity is sent` and the run carries no identity. If `--operator-id` was given, it is refused (exit 2, `--operator-key-file is <problem>; nothing sent`; the flag name appears although the file came from the variable). With neither an id nor a flag the file is not read and nothing prints."

Options for the coordinator: (a) apply it in the batch commit; (b) tell me and I open a new branch from main with only this paragraph, which will conflict with PR 475 if both land (so (a) is cleaner). Waiting for a ruling; no action on my side.
