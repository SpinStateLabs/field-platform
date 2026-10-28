# BACKLOG (self-serve work for idle teammates)

Rule (Don, 2026-10-28: an idle teammate costs real money): when you have no OPEN card in comms/TASK-QUEUE.md, do NOT stop and do NOT wait for the coordinator. Take the lowest-numbered UNCLAIMED item for your role below: edit this file in one commit, replacing `UNCLAIMED` with `CLAIMED <role> <date>` (fetch, rebase, retry on a rejected push; never force-push), then do the work and report in inbox/coordinator/ named by the item id. Read-only unless the item says otherwise. Findings: file:line, HIGH/MEDIUM/LOW. FORCE format (objections, ASSUMPTIONS, REASONING, CONCLUSION). The coordinator may renumber a claimed item into a TASK-QUEUE card later.

## Reviewer (needs GX10 for runs; own worktree under ~/ff-work/, own ports)
- R-01 CLAIMED reviewer 2026-10-28 (covered by C-91, partial; gaps in inbox/coordinator/20261028-2330-reviewer-c91-*): post-merge read of #26 (operator-auth plumbing) at its merge commit; tests plus 5 mutants.
- R-02 CLAIMED reviewer 2026-10-28 (covered by C-91, partial; gaps in inbox/coordinator/20261028-2330-reviewer-c91-*): post-merge read of #27 (ops-console setup area); jsdom tests; XSS surface of the Setup html.
- R-03 CLAIMED reviewer 2026-10-28 (covered by C-91, partial; gaps in inbox/coordinator/20261028-2330-reviewer-c91-*): post-merge read of #30 (GB10 Caddy TLS internal): the `tls internal` site, trust pin, per-tool CA notes.
- R-04 CLAIMED reviewer 2026-10-28 (covered by C-91, partial; gaps in inbox/coordinator/20261028-2330-reviewer-c91-*): post-merge read of #33 (pg-s0 clients, halt and drill banners).
- R-05 CLAIMED reviewer 2026-10-28: ops-console `console.html` (about 1,900 lines) XSS and secret-handling review (C-41 did not read it): innerHTML, eval, URL building, storage of the operator key.
- R-06 DONE reviewer 2026-10-28 (inbox/coordinator/20261029-0130-reviewer-r06-estate-probe.md): `tools/estate_probe.py` full read (never independently reviewed): fail-open paths, proxy handling, output sanitising.
- R-07 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-0730-reviewer-r07-phase-g-check.md): `tools/phase_g_check.py` fail-open read: what a missing or unreachable input reports (must fail closed).
- R-08 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-0800-reviewer-r08-spend-governor.md): spend-governor read plus mutants: D1 throttle, caps, metering failure behaviour.
- R-09 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-0900-reviewer-r09-federation-broker.md): federation-broker read plus mutants: contracts, pubkeys, replay window.
- R-10 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-0930-reviewer-r10-alias-mint.md): delegation-authority mint paths: the alias-mint path (`check_granted_by`, `check_explicitly_listed`) untested per C-2 condition 2; write the probe, list the gap.
- R-11 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-1100-reviewer-r11-kill-switch.md): kill-switch read plus mutants: domain halt, drill, revive; `set_status` on-behalf plumbing.
- R-12 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-1200-reviewer-r12-lifecycle-manager.md): lifecycle-manager `engine.py` read: register, 409 handling, P29 `unchanged` (C-67 left two survivors).
- R-13 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-1330-reviewer-r13-sealed-ledger-retry.md): sealed-ledger `store.py` retry engine read (C-64 LOW survivors at ~L1655-1671): torn read, deadline boundary.
- R-14 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-1400-reviewer-r14-incident-replay.md): incident-replay read plus mutants: timeline, RACI.
- R-15 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-1430-reviewer-r15-attestation-figures.md): attestation-reporter: recompute every figure it emits from source units (tasks/lessons.md rule 1).
- R-16 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-1500-reviewer-r16-compliance-crosswalk.md): compliance-crosswalk: any statement that reads as a compliance claim; citations marked verified without source (lessons rule 4).
- R-17 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-1600-reviewer-r17-field-agent.md): field-agent package (SDK): FieldClient rules 1-5, `canary.py`, `agent.py`, bootstrap; env-proxy and redirect behaviour.
- R-18 PROMOTED to C-141: defence-shield read plus its tests: Agent Incident Retro v0.1.
- R-19 PROMOTED to C-142: `integration/` compose, Caddy and entrypoint files: any service port published, secret in an environment block, or `latest` tag.
- R-20 PROMOTED to C-143: CI workflow `.github/workflows/ci.yml` and `tools/topology_lint.py` current state: unpinned installs, token scopes, what the lint cannot see.
- R-21 DONE reviewer 2026-10-29 (comms/tools/gx10_verify.sh; inbox/coordinator/20261029-1930-reviewer-r21-gx10-verify.md): write the one-command GX10 verify script yourself if card C-47 is still open (tools/gx10_verify.sh or comms/tools/); the coordinator uses ~/ff-work/runhead.sh today (readable on the GX10).
- R-22 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-2030-reviewer-r22-mutation-round.md): adversarial mutation round on the three most recent merges (PRs 58, 59, 61, 63): 20 new mutants each of your own design; report survivors.

## Cloud reviewer (read-only, no GX10; output UNVERIFIED until re-run)
- Q-01 UNCLAIMED: README.md, ROADMAP.md, CHANGELOG.md: every number and date, source it or flag it.
- Q-02 UNCLAIMED: docs/adr/ contradictions with merged code (ADR-0071, 0072, 0074 first, then the rest).
- Q-03 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-2400-reviewer-q03-runbooks.md): docs/runbooks/: every command, path, image tag and volume name that no longer exists on main.
- Q-04 UNCLAIMED: tasks/todo.md (1,900 lines): items still marked open that merged PRs have closed; list with PR numbers.
- Q-05 UNCLAIMED: STATE.md (2,300 lines): statements about what is deployed where, dated; list the ones older than 2026-10-05 that nothing since confirms.
- Q-06 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-2430-reviewer-q06-readme-claims.md): service READMEs under services/*/README.md: claims that exceed what the code enforces ("Enforced vs Declared" rows).
- Q-07 DONE reviewer 2026-10-29 (inbox/coordinator/20261029-2000-reviewer-q07-register-audit.md): the findings register tasks/FINDINGS-2026-10-28.md on comms against inbox/coordinator reports (C-93 if still open).

## Builder (own worktree; draft PR; GX10 run before you ask for review; repo identity; no force-push)
- B-01 UNCLAIMED: any OPEN builder card in TASK-QUEUE.md first; this list only when none is open.
- B-02 UNCLAIMED: a `tools/tests` speed pass: the suite takes 8.5 min; find the five slowest test files (pytest --durations) and propose, not apply, how to split them.
- B-03 UNCLAIMED: a README table in docs/ listing every env variable the services read, from grep, with file:line; flag undocumented ones.
- B-04 UNCLAIMED: dead-code report: functions in packages/ and services/ never referenced (vulture-style, by grep); report only.


