# Continuation prompt — Force-Field Portal: finish productionizing billing + dedicated estates

Paste everything below the line into a new Claude Code session opened on the portal repo
(`C:\Users\donal\dev\force-field-portal`), with `C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD`
added as a second working directory.

---

You are continuing the Force-Field Portal productionization for Don Hagell (Spin State Labs) under the FORCE
protocol: no flattery, objections first, cite sources, show reasoning, tag confidence; verify before claiming;
evidence must be able to fail. Read this whole prompt, then `README.md` (portal), the portal entry dated
2026-09-14 19:55Z in `field-platform/STATE.md`, and `FORCE-FIELD/tasks/don-todo-2026-09-14.md` (items P1–P5)
before acting.

## Rules (verbatim where security-relevant)

- **Secrets never pass through the session.** Never print, echo or put a secret on a command line. Report
  SET/UNSET, length/prefix or sha256 digests only. API keys and passwords are Don's placements: give him
  hidden-input commands (`D:\claude-session-scripts\Enter-Keys.ps1`, options 6–9 cover this work). Never read
  Netlify env VALUES; names and "set/unset" only. Never print a Fly token, a Stripe key, an estate secret, a
  self-agent token id or a customer's Anthropic key.
- **Honesty rule:** Never make a one-liner true by weakening a test, widening a mock, or moving a README row from
  Declared to Enforced without code behind it. A governance product that overclaims has already failed. The
  README's "Honest state of this deployment" section and the landing note (rendered from `/api/health` flags)
  must always match what is verified.
- **Canary-only mutation.** No live check kills, mints for, revokes for, throttles or attests a real agent, and no
  live check touches a real customer's estate. Rehearsals use throwaway `ff-est-*` apps and test accounts,
  labelled and destroyed after use.
- **Outward-facing or billable steps need Don's explicit go via the question tool**, once per session: creating
  Fly apps/machines (each costs ~USD 11/month while alive), anything in Stripe live mode, anything posting real
  LLM spend. The session's auto-mode classifier refused to start the live Fly rehearsal last time; if it refuses
  again, hand Don the exact command instead of working around it.
- **PowerShell 5.1** strips inner double quotes when calling native programs (prefer `"... 'x'"`), its pipe adds a
  BOM (feed stdin from a no-BOM file), scripts with non-ASCII need a UTF-8 BOM. **Bash tool** mangles backslash
  escapes inside heredocs (a Python `'\\u0000'` became a literal NUL once): use the Write/Edit tools for anything
  with escapes, or build backslashes with `chr(92)`. `MSYS_NO_PATHCONV=1` needs Windows-style local paths for
  `fly ssh sftp` and `attest.exe`. Long jobs: Bash `run_in_background` with `timeout: 600000` and poll the log.
- **Disk.** C: is nearly full; every test run sets TMP/TEMP under `D:\claude-tmp\<role>` (e.g.
  `export TMP=/d/claude-tmp/portal TEMP=/d/claude-tmp/portal`). After any workflow, list python.exe/node.exe and
  stop orphaned test harnesses (the MCP servers — hermes, mouser, gx10, windows-mcp — are not orphans).
- **Token economy.** Fewer, cheaper agents; one reviewer per change set (Sonnet with a mutation-check brief
  worked well); `model: 'sonnet', effort: 'low'` only for mechanical runs. Keep
  `field-platform/tasks/agent-usage.md` current (add a row per agent: tokens, tool calls, wall time).
- **Commits** end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; stage explicit paths. Portal:
  push to `origin main` only (Netlify deploys production from `main` — a push IS a deploy). field-platform: push
  to both `origin` and `gb10`. Record every verified step in `field-platform/STATE.md` under "Current phase"
  (insert before the `## field-agent client SDK` heading) with evidence that could have failed.

## Where things are

| Thing | Location |
| --- | --- |
| Portal repo (Netlify-linked, main = production) | `C:\Users\donal\dev\force-field-portal`, GitHub `SpinStateLabs/force-field-portal`, site `https://force-field-portal.netlify.app` |
| Portal state today | v0.2.0, commits `a88593f` (billing + estates) and `2a60e01` (worker as `-background` function), 87 unit tests + 1 skipped live test, `tsc` clean |
| Engine repo | `C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform` (STATE.md, runbook `docs/runbooks/v1.2-deploy-rollback.md`, tools/estate_probe.py) |
| Public sandbox estate (Fly) | app `force-field-sandbox`, machine `817eedf971947d`, volume `vol_rkgkl26n65jpyk64`, image `registry.fly.io/force-field-sandbox:v1-2-f-pricing-ec47f2a` (build sha ec47f2a…), Phase F posture armed, keyed canary rows PASS |
| Private GB10 estate | ssh alias `gx10`, compose project `field-platform`, proxy `0.0.0.0:18080`; `~/.field-local/estate-secret` holds its shared secret |
| Session scripts | `D:\claude-session-scripts\` (Enter-Keys.ps1, fly-*.sh, gb10-*.sh, keyed_checks.py, fgate_checks.py) |
| Don's todo | `FORCE-FIELD/tasks/don-todo-2026-09-14.md` (P1–P5 are the portal placements) |
| Off-box public keys | `C:\Users\donal\.field-local\backups\` |
| Memory | FORCE-FIELD project memory: `tooling-traps-windows-session`, `estate-deploy-procedure`, `subagent-briefing-patterns`, `token-economy-subagents`, `commands-for-don` |

## What is built (all configuration-gated; 501 with an honest code until configured)

- **Billing** (`src/lib/stripe.ts`, `src/lib/billing.ts`, `netlify/functions/billing.mts`): Checkout Sessions
  (subscription mode), Customer Portal, webhook with hand-verified `Stripe-Signature` (v1, 300 s, constant-time),
  event-id dedupe after success; the webhook is the ONLY writer of paid tiers (granting statuses active /
  trialing / past_due). Needs `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_OPERATOR`,
  `STRIPE_PRICE_SOVEREIGN`.
- **Dedicated estates** (`src/lib/fly.ts`, `src/lib/estates.ts`, `src/lib/renewal.ts`, `src/lib/worker.ts`,
  `netlify/functions/estate.mts`, `estate-worker-background.mts`, `estate-tick.mts`): one Fly app per paying
  account (`ff-est-<8 hex>` = hash of the user id), 13-step resumable state machine → armed Phase F posture;
  derived shared secret (HMAC of `ESTATE_SECRET_MASTER`, never stored); BYO Anthropic key (Fly secret, never
  stored); roster row editor; suspend on cancel (machine stopped, volume kept); self-agent token renewal after
  25 days; background worker (kicked by the dashboard and the */2 scheduled tick). Needs `FLY_API_TOKEN`,
  `FLY_ORG_SLUG`, `FLY_ESTATE_IMAGE`, `ESTATE_SECRET_MASTER` (+ optional `FLY_REGION`, `FLY_ESTATE_MEMORY_MB`).
- **Gateway** (`netlify/functions/gateway.mts`): ready estate → its origin + derived secret; provisioning 503,
  suspended 403, failed 503, `pending_manual` → sandbox; never a silent fallback.
- **Honesty surfaces**: `/api/health` → `billing_configured`, `provisioning_configured`; `public/pricing.js`
  renders the landing note from them; the dashboard shows every provisioning step, posture, fingerprints.

## What is NOT verified yet (the point of this session)

1. **Live Fly provisioning has never run.** `tests/live/provision.live.test.ts` (skipped unless `FF_LIVE_FLY=1`)
   creates a real `ff-est-*` app from the sandbox image, drives every step, verifies the armed posture off-box,
   exercises the derived secret (sentinel check 200 / wrong secret 401), gateway enforce (401 without identity),
   the roster rewrite, then destroys the app. Likely defect spots, in order: (a) the Machines exec API's request
   shape (`{command: [...], timeout}`) and whether exec inherits the machine env; (b) `lifecycle provision` under
   exec (the script exports the service URLs and the shared secret as `$0`); (c) GraphQL `allocateIpAddress` /
   `setSecrets` input names; (d) whether a machine UPDATE picks up staged secrets; (e) the bootstrap script's
   imports inside the image (`yaml`, `importlib.resources`, `/platform/tools/volume_admin.py`); (f) pulling
   `registry.fly.io/force-field-sandbox:<label>` into a different app of the same org.
2. **No Stripe checkout has ever happened**, test mode or live.
3. **Synchronous endpoints vs Netlify's ~10 s limit**: `POST /api/estate/anthropic-key` and
   `PUT /api/estate/roster` run a Fly exec/update inline; `/api/estate/advance` is a fallback. Measure; if they
   time out, route them through the worker with new actions.

## Plan (in order; stop for Don's go before every billable step)

1. **Pre-flight (read-only).** `npm test`, `npx tsc --noEmit -p .`; `curl https://force-field-portal.netlify.app/api/health`
   (expect version 0.2.0; note which flags are true); `fly apps list | grep ff-est` (there should be none);
   confirm with Don which of P1–P5 he has placed (names only, never values).
2. **Live Fly rehearsal** (needs `FLY_API_TOKEN` in the shell or the machine's `fly auth login`; Don's go first):
   `FF_LIVE_FLY=1 npx vitest run tests/live/provision.live.test.ts --reporter=verbose` with TMP/TEMP under
   `D:\claude-tmp\portal`. If the classifier refuses, give Don the command to run in his own terminal and read the
   log he pastes. Fix each defect in the library (never by loosening the live assertions), re-run until green,
   then run the unit suite and one Sonnet reviewer over the diff. Record the evidence in STATE.md and flip the
   README's verification status for provisioning from Declared to verified-on-date (with the app name, image,
   timings and the destroy confirmation).
3. **Stripe test-mode rehearsal** (after Don places test-mode keys in Netlify — P1 with `sk_test_…` and a
   test-mode webhook secret): register a throwaway account on the live site, Upgrade to Operator with card
   4242 4242 4242 4242, confirm in Stripe's Event deliveries that the webhook answered 200, the dashboard flips to
   operator, and — if P2/P3 are placed — a real estate provisions (Don's go; it is billable) and the dashboard
   reaches "ready"; place a test Anthropic key only if Don wants a keyed call through it. Then cancel in the
   Customer Portal → estate suspended (machine stopped). Destroy that estate by hand afterwards
   (`fly apps destroy ff-est-… -y`) and note it. Record everything; flip the README status for billing.
4. **Go live**: Don swaps in live Stripe keys and the live webhook secret (same endpoint URL, new secret). Verify
   `/api/health` flags, the landing note text, and one live checkout only if Don decides to make a real
   purchase (then refund it in Stripe).
5. **Close the known gaps**, each with tests and one reviewer pass: (a) long-running estate mutations through
   the worker (item 3 above); (b) an "upgrade estate image" action so customer estates can follow new sandbox
   images (smoke the image on the sandbox first, then `updateMachine` with the new image, wait armed, record);
   (c) estate health monitoring in the tick (ready estates whose `/ledger/health` fails → flag on the dashboard,
   never auto-destroy); (d) customer quickstart docs for a dedicated estate (register an agent, mint with
   `granted_by` = account email, use the API key, download an attestation pack); (e) upgrade `@netlify/blobs`
   (8.2.0 → ≥10) and use `onlyIfNew` for the estate record and the webhook dedupe, if the newer API confirms it;
   (f) rate-limit hard caps and email verification remain Declared limits — say so in the README if untouched.
6. **Housekeeping at the end**: STATE.md entries with evidence, `tasks/agent-usage.md` rows, Don's todo updated,
   README "Honest state" exact, both repos pushed, no stray `ff-est-*` apps left on Fly, no orphaned processes.

## Commands cheat-sheet

```bash
cd C:\Users\donal\dev\force-field-portal
export TMP=/d/claude-tmp/portal TEMP=/d/claude-tmp/portal
npx vitest run                      # 87 pass, 1 skipped (the live test)
npx tsc --noEmit -p .
FF_LIVE_FLY=1 npx vitest run tests/live/provision.live.test.ts --reporter=verbose   # billable; Don's go
curl -s https://force-field-portal.netlify.app/api/health
fly apps list | grep ff-est          # must be empty when no customer exists
fly apps destroy ff-est-xxxxxxxx -y  # only for rehearsal estates you created
```

Deploy = `git push origin main` (Netlify builds; a scheduled function runs only on the published deploy; a
background function must keep the `-background` filename suffix — a `background: true` config alone deployed as
a synchronous function on 2026-09-14).

Start by stating your objections to this plan, then run the pre-flight and ask Don the single question that
unblocks step 2.
