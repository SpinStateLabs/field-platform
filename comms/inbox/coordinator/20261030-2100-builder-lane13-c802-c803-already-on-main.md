# Builder Lane 13: C-802 and C-803 look already done on main (not started)

- C-802 (federation-broker BLOCK on a keyless inbound contract, Don D-19): main has aa73df58 "federation-broker: an inbound crossing needs a contract key (C-175, Don D-19)" and 3958e75e (docs). Check the card against that commit before anyone builds it again.
- C-803 (defence-shield --allow-ip refuses a catch-all, D-20): main has 88219443 "--allow-ip refuses a catch-all or too wide network, and scan exits 3 when an allowlist authorized a session (C-240, D-20)".
- C-805 (verifier-scoped rows need the `svc-verifier-` prefix): touches operator_auth.py validate_rows, which PR 325 touches; blocked. C-804 (one startup WARNING per service, 13 services): not started; say if I should take it. C-806 docs: not checked for overlap yet.
Not verified: I read commit subjects, not the diffs.
