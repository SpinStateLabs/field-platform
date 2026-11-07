# Don's answers on Stage 3 preparation (chat, question tool, 2026-11-07 ~05:00Z; recorded by the coordinator)

Source report: comms/inbox/coordinator/20261107-0430-estate-deployer-stage3-prep.md

1. Line 18 (the two Windows renewal tasks token-renewal-ssl-invoicing-agent and token-renewal-ssl-timekeeping-agent carry --operator-id job-renewal-rog with key file job-renewal-rog.key; the coordinator read the task definitions on rog-command, secrets masked): CONFIRMED by Don, record it as his.
2. GB10 renewal job: YES, the deployer fixes it on the host (crontab --operator-id job-renewal-gb10 and replace ~/vt-renewal/renew_token.py with tools/renew_token.py). Back up the old crontab and script first; no key printed.
3. PR 837 (Stage 2 window judge): YES, HOLD Stage 3 until 837 is fixed (reviewer condition: evaluate must require all eight service labels) and merged to main.
4. Stage 3 timing: "Tell me when it is ready". Nothing is authorised yet: when 837 is merged and the renewal job is fixed, the coordinator asks Don for the go sentence `GO STAGE 3 <sha8>` and the live R-1 rehearsal with Don present (his key and break-glass).
Stage 2 stays armed and monitored. Fly Stage 4b and the Fly redeploy are not authorised.
