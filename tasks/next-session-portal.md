# Next session — Force-Field Portal: Stripe test-mode rehearsal and go-live (written 2026-09-14 ~23:05Z)

Paste the block below into a new session opened on `C:\Users\donal\dev\force-field-portal` with the FORCE-FIELD folder as a
second working directory. Copy in `field-platform/tasks/next-session-portal.md`.

```markdown
You are continuing the Force-Field Portal productionization for Don Hagell (Spin State Labs) under the FORCE
protocol: no flattery, objections first, cite sources, show reasoning, tag confidence; verify before claiming;
evidence must be able to fail. Read this whole prompt, then `README.md` (portal, "Honest state of this deployment"),
the portal entries dated 2026-09-14 22:06Z and 22:33Z→22:58Z in `field-platform/STATE.md`, and
`FORCE-FIELD/tasks/don-todo-2026-09-14.md` (P1–P5) before acting.

## Rules (verbatim where security-relevant)

- **Secrets never pass through the session.** Never print, echo or put a secret on a command line. Report
  SET/UNSET, length/prefix or sha256 digests only. API keys and passwords are Don's placements: give him
  hidden-input commands (`D:\claude-session-scripts\Enter-Keys.ps1`, option 8 opens the Stripe pages). Never read
  Netlify env VALUES; names and "set/unset" only. Never print a Fly token, a Stripe key, an estate secret, a
  self-agent token id or a customer's Anthropic key. Throwaway-account passwords are generated in-process
  (`python -c "import secrets; ..."` into a shell variable) and discarded.
- **Honesty rule:** never make a one-liner true by weakening a test, widening a mock, or moving a README row from
  Declared to Enforced without code behind it. The README's "Honest state" section and the landing note (rendered
  from `/api/health` flags) must always match what is verified.
- **Canary-only mutation.** No live check kills, mints for, revokes for, throttles or attests a real agent, and no
  live check touches a real customer's estate. Rehearsals use throwaway `ff-est-*` apps and throwaway accounts,
  labelled and destroyed after use.
- **Outward-facing or billable steps need Don's explicit go via the question tool**, once per session: creating
  Fly apps/machines (~USD 11/month each while alive), anything in Stripe live mode, anything posting real LLM spend.
  In bypass-permissions mode the classifier did NOT refuse the live Fly run; if it does, hand Don the exact command.
- **Live cloud runs**: launch DETACHED so no tool timeout can kill the test's cleanup — PowerShell
  `Start-Process npx.cmd -ArgumentList 'vitest run tests/live/provision.live.test.ts --reporter=verbose'
  -WorkingDirectory C:\Users\donal\dev\force-field-portal -RedirectStandardOutput D:\claude-tmp\portal\live-N.log
  -RedirectStandardError D:\claude-tmp\portal\live-N.err -NoNewWindow -PassThru` after `$env:FF_LIVE_FLY='1';
  $env:TMP='D:\claude-tmp\portal'; $env:TEMP=$env:TMP; $env:NO_COLOR='1'`, then a `Monitor` tailing the log for
  `progressed|error |final status|destroyed|Test Files`. The Bash tool blocks foreground `sleep`; wait via Monitor or a
  `run_in_background` until-loop. After every run: `fly apps list | grep ff-est` must be empty.
- **PowerShell 5.1** strips inner double quotes when calling native programs; its pipe adds a BOM; scripts with
  non-ASCII need a UTF-8 BOM. **Bash tool** mangles backslash escapes in heredocs: use Write/Edit for anything with
  escapes. **Netlify CLI is broken on this box** (missing module): use `/api/health`, `curl`, and the Netlify UI.
- **Disk.** C: is nearly full; set `TMP`/`TEMP` under `D:\claude-tmp\portal` for every test run. After any workflow,
  list node.exe/python.exe and stop orphaned test harnesses (MCP servers — hermes, mouser, gx10, windows-mcp,
  desktop-commander, pdf — are not orphans).
- **Token economy.** Fewer, cheaper agents; one Sonnet reviewer per change set with a mutation-check brief (five
  mutations applied/observed/reverted worked twice today); keep `field-platform/tasks/agent-usage.md` current.
- **Commits** end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; stage explicit paths. Portal:
  push to `origin main` only (a push IS the production deploy; `/api/health` `version` proves it landed after a
  version bump in `netlify/functions/health.mts` + `package.json`). field-platform: push to `origin` and `gb10`.
  Record every verified step in `field-platform/STATE.md` under "Current phase" (before `## field-agent client SDK`).

## Where things are

| Thing | Location |
| --- | --- |
| Portal repo (Netlify-linked, main = production, public) | `C:\Users\donal\dev\force-field-portal`, GitHub `SpinStateLabs/force-field-portal`, site `https://force-field-portal.netlify.app` |
| Portal state | v0.2.1: commits `b6b1d63` (live-rehearsal fixes), `ce835e7` (health looks, image rollout, lifecycle roster, gateway identity headers, blobs 11 conditional writes, quickstart), `d51cefd` (strong-consistency reads); 104 unit tests + 1 live test; `tsc` clean |
| Engine repo | `C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform` (STATE.md; `tasks/portal-live-fly-rehearsal-2026-09-14.log` = the four live runs) |
| Public sandbox estate (Fly) | app `force-field-sandbox`, machine `817eedf971947d`, image `registry.fly.io/force-field-sandbox:v1-2-f-pricing-ec47f2a` (= `FLY_ESTATE_IMAGE`) |
| Netlify env (names only) | `SESSION_SECRET`, `ESTATE_URL`, `ESTATE_SHARED_SECRET`, `FLY_API_TOKEN`, `FLY_ORG_SLUG`, `FLY_ESTATE_IMAGE`, `FLY_REGION`, `ESTATE_SECRET_MASTER`, `NODE_VERSION` (from netlify.toml). NO `STRIPE_*` yet (P1) |
| Session scripts | `D:\claude-session-scripts\` (Enter-Keys.ps1 option 8 = Stripe pages) |
| Don's todo | `FORCE-FIELD/tasks/don-todo-2026-09-14.md` (P1 open; P2–P4 done/updated) |
| Memory | FORCE-FIELD project memory: `portal-productionization`, `tooling-traps-windows-session`, `estate-deploy-procedure`, `commands-for-don`, `token-economy-subagents` |

## Verified today (do not re-verify; cite)

- Live Fly provisioning: four throwaway runs, green; an estate reaches `ready` in 58–80 s; posture, fingerprints,
  staged secrets, derived secret 200/401, gateway 401 without identity, roster rewrite, lifecycle roster armed,
  health look ok, forced image re-apply (27 s) all verified off-box; every app destroyed. Evidence: the log above and
  the README's verification status. Caveat that stands: every run used the operator's `fly auth login` token, so the
  org token in Netlify is first exercised by the first real (test-mode) checkout.
- Defects found and fixed in the library (never the assertions): shared-IPv4 GraphQL payload; an empty customer
  roster row invalidating the fail-closed DOA roster; the portal gateway dropping `x-field-agent-id`/`x-field-token`
  (every governed LLM call would have been 401); customer estates lacking `FIELD_LIFECYCLE_ROSTER`; Netlify Blobs
  reads eventually consistent by default (a registration's own follow-up read missed the user for ~13 s; fixed with
  `consistency: "strong"` in d51cefd — check STATE.md 22:33Z entry's last line for the production re-probe result).
- Throwaway accounts left in the production store (sandbox tier, harmless, no admin delete exists):
  `ff-deploycheck-20260914224701@example.com`, `ff-deploycheck-b-20260914224740@example.com`, and the
  `ff-deploycheck-c*` ones from the re-probe. List them in any cleanup design.

## Still Declared (honesty rule)

1. **No Stripe checkout has happened** (test mode or live). `billing_configured` is false on the live site.
2. The Netlify org-scoped Fly token has never created an app.
3. Rate limits are approximate counters; no email verification; sessions not server-revocable; per-step and worker
   leases are read-then-write (only record creation and webhook claims are create-only writes).
4. The engine-image rollout has been exercised only as a forced re-apply of the same image; a real label change has
   not been rolled out to a customer estate (there are none).

## Plan (in order; stop for Don's go before every billable step)

1. **Pre-flight (read-only).** `npm test` (104 pass, 1 skipped), `npx tsc --noEmit -p .`,
   `curl -s https://force-field-portal.netlify.app/api/health` (expect version 0.2.1, `provisioning_configured`
   true), `fly apps list | grep ff-est` (must be empty). Confirm with Don by NAME only whether the four `STRIPE_*`
   test-mode variables exist in Netlify (P1: `sk_test_…`, the test-mode webhook signing secret, two test Prices).
2. **Stripe test-mode rehearsal** (after P1 and a redeploy so the functions see the variables; `billing_configured`
   must read true): register a throwaway account on the live site (password generated in-process), Upgrade to
   Operator with card 4242 4242 4242 4242, confirm in Stripe's Event deliveries that the webhook answered 200, the
   dashboard flips to operator, and — with Don's go, it is billable — a real estate provisions THROUGH THE SITE (this
   is the first exercise of the Netlify org token) and reaches "ready" (watch the dashboard log; the background
   worker and the */2 tick drive it). Place a test Anthropic key only if Don wants a keyed call through it. Then cancel
   in the Customer Portal → the estate suspends (machine stopped, volume kept) → verify with `fly machine list -a
   ff-est-…`. Destroy that estate by hand (`fly apps destroy ff-est-… -y`) and note that its record now shows the
   honest "app missing" error on the next tick (health look). Record everything; flip the README status for billing.
3. **Go live**: Don swaps in live Stripe keys and the live webhook secret (same endpoint URL, new secret); verify
   `/api/health` flags and the landing note; one live checkout only if Don decides to make a real purchase (refund it
   in Stripe afterwards).
4. **Remaining gaps**, each with tests and one reviewer pass: (a) an operator cleanup path for throwaway accounts and
   destroyed estates (no admin auth exists — design it, do not bolt on a footgun); (b) compare-and-swap on record
   UPDATES using `onlyIfMatch` + `getWithMetadata` etags (blobs 11 supports it) for the step/worker leases;
   (c) a real image-label rollout rehearsal when the sandbox next ships a new label (smoke it there first);
   (d) email verification and server-revocable sessions stay Declared — say so if untouched.
5. **Housekeeping at the end**: STATE.md entries with evidence, `tasks/agent-usage.md` rows, Don's todo, README
   "Honest state" exact, both repos pushed, no stray `ff-est-*` apps, no orphaned processes.

Start by stating your objections to this plan, then run the pre-flight and ask Don the single question that
unblocks step 2.
```
