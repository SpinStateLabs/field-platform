# Continuation prompt — FIELD v1.2, Phase F (written 2026-09-14)

Paste everything below the line into a new Claude Code session opened in
`C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform`.

---

Continue the FIELD platform v1.2 production build with **Phase F**. Run under the FORCE protocol: no flattery, objections first, cite sources, show reasoning, and tag confidence. Verify before claiming; evidence must be able to fail.

## Read first, in this order
1. `STATE.md` (top sections): what is live on each estate, with evidence. The newest entry is "Phase D + X3 DEPLOYED on both estates, 2026-09-14".
2. `tasks/todo.md`:
   - REVISION 2.1 at the top: rules 1–8, the arming table A7–A12, the reversibility table, and "Still needs Don".
   - "- [ ] **Phase F**" (build items + F-gate adds).
   - The detailed "### Phase F" section (F1 gateway egress enforcement, F2 per-event ledger signatures, F3 spend REWORD, F4 served attestation signing).
3. `docs/runbooks/v1.2-deploy-rollback.md`: §2 GB10 deploy, §4 canary / arming / X3 / X4 sections, §5 Fly deploy.
4. `tasks/agent-usage.md` and the memory index: Don's standing preferences (token economy, disk).

## Where things stand (verify, don't trust)
- **Code:** `main` at `d2e59fc` or later, pushed to `origin` (GitHub SpinStateLabs/field-platform, public — read CI through `https://api.github.com/repos/SpinStateLabs/field-platform/actions/runs?head_sha=<sha>`) and the `gb10` remote.
- **Done and live on both estates:** Phases A, B, C (incl. the one-time ledger rotation + A4 anchor keys), D, X0, X1 (A1 owners roster, A2 GB10 perimeter secret, A3 DOA roster), X4 (witness direction 1, A5). X3 + A6 are live on the GB10 only.
- **GB10** (private, `ssh gx10`, `~/field-platform`, compose project `field-platform`, proxy `127.0.0.1:18080`):
  - Deployed build `8f1c0df`.
  - Switches live in `integration/demo/.env`; compose ignores `~/field-platform/.env`. Never print that file: it holds secrets.
  - `COMPOSE_PROFILES=witness,x3`.
  - Perimeter secret file: `~/.field-local/estate-secret`.
  - Shared host (SpinTrader, TimescaleDB, open-webui…): scope every command to the project and never prune.
  - The vt cron runs at `5 */4 * * *` local time (America/Toronto): don't deploy between :05 and :20 of those hours.
  - Deploy/check scripts: `~/field-backups/*.sh`, `*.py` (`gb10-deploy.sh <label> <full sha>` does tags, save, backup-verify, recreate and verify).
- **Fly** (public `force-field-sandbox`, one machine `817eedf971947d`, volume `vol_rkgkl26n65jpyk64`, 2 GB):
  - Release v8, image `v1-2-d-8f1c0df`. Secrets: `FIELD_SHARED_SECRET`, `FIELD_LIFECYCLE_ROSTER`, `FIELD_DOA_ROSTER`, `ANTHROPIC_API_KEY`.
  - Deploy: build-only push with `--build-arg FIELD_BUILD_SHA` from a clean `git worktree`, then a service-less smoke machine, then a snapshot, then `fly deploy --image`.
  - `fly ssh sftp put` never overwrites: use fresh `/tmp` names. `fly secrets set` restarts the machine and clears `/tmp`.
- **rog-command (this PC):**
  - Token renewal is installed: vt via GB10 cron 14:35 local; both ssl agents via Task Scheduler `\FIELD\` at 14:50/15:05, Interactive logon, `--secret-file`.
  - The GB10 secret copy is `C:\Users\donal\.field-local\gb10-estate-secret`.
  - Backups, anchors and public keys are in `C:\Users\donal\.field-local\backups\`.
  - Last session's helper scripts (Fly D-gate, throttle, C-gate checks, usage report) are in `D:\claude-session-scripts\` (`usage_report.py` has the old session id hard-coded: edit it).

## Open items blocking or shaping Phase F (ask Don where marked)
- **Don — Anthropic API credits.** On both estates the keyed gateway call returns HTTP 400 "credit balance is too low". Keys are placed and the gateway is not mocked. Keyed evidence (usage attribution, F1 allow-and-forward, the judges D14, A12) waits on credits.
- **Don — GB10 `osfi-e23` false stale flag.** A manual `check-file` run after the live baseline flagged it, and it blocks pack generation on the GB10. If STATE.md doesn't show it cleared, check with `docker exec field-platform-crosswalk-1 crosswalk regwatch status` and ask Don to run the clear with his name.
- **Don:**
  - D3 owners-roster confirmation (armed provisionally);
  - D5 Fly secret on the GB10 (X4 direction 2);
  - D7 second Fly app (X3 on Fly);
  - D9 custody of the F2/F4 signing keys (anchor keys were on-box / pubkey off-box);
  - D10 F4 signer name;
  - D12 CLI via gateway;
  - D14 arm the judges;
  - D15 vt manifest seal_algorithm;
  - D16 Phase G positive path;
  - Netlify `ESTATE_SHARED_SECRET`;
  - the ssl SKILL.md hook-2 re-upload;
  - field-agent plugin 0.1.2 reinstall;
  - vt token `035e4087…` (expires 2026-09-19).
- **Soak evidence still to record:** the first scheduled lifecycle `swept_at` and a later witness anchor. Every recreate restarts both intervals; the last recreate was 2026-09-14 ~04:21Z (GB10) and ~04:25Z (Fly).

## Phase F — what to do
Follow the plan text exactly: **F2 must ship first** (J1), then F1, F2b, F3 (REWORD), F4, the egress network, and arming A7 → A8 → A9 → A10 → A11 with a canary and a ≥ 1 h GB10 soak per step before Fly. Irreversible steps need Don's explicit go before they run:
- A7's first signed event makes pre-F2 ledger images unable to start;
- A9 `REQUIRE_SIGNING=1`;
- anything posting real spend.

State them plainly, with what rollback can and cannot undo, and ask with a question tool before crossing them.

Suggested shape, economical per Don:
1. **Understand:** read the plan's F sections and the current code paths they touch. Do it yourself or with ONE explore agent.
2. **Build:** parallel builders only where file ownership is disjoint (e.g. F2 ledger + sentinel; F1 gateway + compose egress network; F4 attestation). Each gets one medium-effort reviewer and a fixer only if needed. Then one verifier. Apply shared-file edits (compose, entrypoint, ci.yml, docs, plan) in one serialized integration step afterwards.
3. **Ship:** commit in logical groups, push, read CI via the API, deploy GB10 then Fly with the scripts above, then run the F-gate adds and the arming canaries. Record everything in STATE.md and tick `tasks/todo.md`.

## Rules that bit last session
- **Secrets never pass through the session.** Never print, echo or put a secret on a command line. Report SET/UNSET, length/prefix or sha256 digests only. API keys and passwords are Don's placements: give him hidden-input commands.
  - PowerShell 5.1 strips inner double quotes when calling native programs: prefer `"... 'Don Hagell'"` quoting in commands you hand him.
  - Its pipe adds a BOM, so feed stdin from a no-BOM file.
- **Canary-only mutation.** No live check kills, mints for, revokes for, throttles or attests a real agent. Synthetic data is labelled and deactivated after use.
- **Disk.** C: is 119 GB and near full; D: has ~600 GB free.
  - Every test run and every workflow agent must set `TMP`/`TEMP` and pytest `--basetemp` under `D:\claude-tmp\<role>`.
  - After each workflow, list `python.exe` processes and stop orphaned test harnesses (`estate_harness`, `ledger_c2_harness`, multiprocessing workers). They filled the disk last time.
- **Token economy (Don).** Fewer, cheaper agents. One reviewer per change set. `model: 'sonnet'`, `effort: 'low'` only for mechanical command runs, and check its output is a real result, not "I'll wait for the monitor". Medium effort for re-verifiers. Keep `tasks/agent-usage.md` / a usage report current. Up to ~15 agents for a parallel phase is approved; 100 is not useful.
- **Workflow resume.** A prompt that embeds results of parallel agents must serialise them in a fixed key order, or a resume re-runs that agent (a cache miss).
- **Honesty rule, verbatim:** "Never make a one-liner true by weakening a test, widening a mock, or moving a README row from Declared to Enforced without code behind it. A governance product that overclaims has already failed."
- **Commits** end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`; stage explicit paths; push to both `origin` and `gb10`.

Start by confirming the live state of both estates read-only (health with `--expect-perimeter --expect-build-sha`, continuity to a fresh pin, the witness and X3 still up, the osfi-e23 flag). Then post a short Phase F plan with objections first and the irreversible steps named, and ask Don only the questions that block F2.
