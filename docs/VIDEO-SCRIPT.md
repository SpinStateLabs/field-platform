# FIELD Platform — Capstone Demo Video Script

**Use this document as:** a shooting script for a screen recording (OBS /
Camtasia), a teleprompter script for voiceover, or a prompt for an AI
video/voiceover tool. Everything on screen is a real command with a
verified output — record live, do not mock.

---

## Production brief

- **Title:** *Declared vs. Enforced — the FIELD Platform in four minutes*
- **Audience:** UWaterloo AI-CTO capstone evaluators; C-level buyers
  (CISO/CFO/GC/CIO). Assume smart, skeptical, allergic to hype.
- **Length:** 4:00 target (a 0:60 cut list is at the end).
- **Tone:** FORCE rules apply to the narration itself — no filler, no
  superlatives, lead with the claim, show the evidence. Plain voice,
  measured pace (~140 wpm).
- **Visuals:** terminal (dark theme, ≥18 pt monospace, 1080p+) and a
  browser on the ops console. No slides except the title and close cards.
- **Prep before recording (~5 min):**
  1. Activate the venv; confirm `pytest` is green.
  2. `bash integration/demo/run_demo.sh` once as a dry run, then reset.
  3. Keep `bash services/ops-console/demo.sh` ready in a second terminal.
  4. Browser tab ready at `http://127.0.0.1:8011/` (loads once the console
     demo is up).

---

## SCENE 1 — Cold open: the problem (0:00–0:30)

**[SCREEN]** Title card, 3 s: *"Your AI agents have job descriptions.
Who enforces them?"* Then cut to a terminal showing
`integration/demo/manifests/invoicing-agent.yaml` scrolling slowly —
pause on `kill_switch:`, `spend_cap:`, `scope:`.

**[VO]**
> Enterprises are deploying AI agents with real authority — reading
> ledgers, drafting invoices, talking to customers. Most governance for
> those agents is a document: a policy that *declares* what the agent may
> do. This is one of ours — a FIELD manifest. Kill switch. Spend cap.
> Delegated scope. But a declaration is not a control. The FIELD Platform
> is what makes this manifest *enforced* — and it is honest, everywhere,
> about which guarantees are code and which are still promises.

---

## SCENE 2 — One command, the whole story (0:30–1:45)

**[SCREEN]** Run:

```bash
bash integration/demo/run_demo.sh
```

Let it play. Zoom/callout on each moment as the narration hits it
(the run takes ~23 s; pause the recording between callouts as needed).

**[VO]** (timed to the output)
> One command boots seven governance services and puts a deliberately
> mundane agent — an invoicing copilot — under governance.
>
> Its manifest validates. It's registered to a **human owner**. Its spend
> cap comes straight from the manifest: five hundred dollars a day. A
> human mints its authority: a scoped token, expiring in one hour.
>
> Watch it work. Four invoices drafted — every action checked, every
> check written to a tamper-evident ledger, every dollar metered.
>
> **[callout: INV-005 ESCALATED E.spend_threshold]** The fifth draft
> arrives with the meter at ninety-six percent of cap. It is not blocked —
> it *waits for a human*. Escalation before the wall, not after.
>
> **[callout: BLOCKED D.scope]** Now the agent tries something it was
> never granted: transfer funds. Blocked — and the refusal cites the
> exact clause: delegation scope. The function body never executed.
>
> **[callout: drill timings]** The two-a.m. question — can you stop it? —
> has a measured answer: kill confirmed in about forty milliseconds,
> verified and restored in under sixty.
>
> **[callout: chain intact: True]** Fifteen events. One hash chain.
> Intact.

---

## SCENE 3 — The dashboard: harnessing the fleet (1:45–2:45)

**[SCREEN]** Second terminal: `bash services/ops-console/demo.sh`.
Switch to the browser at `http://127.0.0.1:8011/`. Show the three-agent
fleet, the escalation queue, the live ledger tail. Then, on camera:
1. In the **harness**, select `invoicing-agent`, its token, type
   `transfer funds`, click *ask the sentinel* → red **BLOCK [D.scope]**.
2. Click **kill** on an agent, type an operator name, watch the status
   flip and the `kill.agent` event appear in the ledger tail.
3. Click **resolve** on the escalation, enter a name.

**[VO]**
> This is the ops console — the human's side of the harness. Every
> governed agent, its owner, its tokens, and the escalation queue where
> agents wait for people.
>
> The harness lets you ask the enforcement engine what *would* happen —
> and the verdict is real: it lands on the audit ledger like any other
> check.
>
> The kill button is not a UI feature. The console holds no authority of
> its own — every button goes through the same services, with your name
> recorded on the ledger. Delete the dashboard and the governance model
> doesn't change. That's by design.

---

## SCENE 4 — Try to cheat it (2:45–3:25)

**[SCREEN]** Terminal, staged ledger file. Run in order:

```bash
ledger verify --path demo-events.jsonl
# OK — chain intact over 5 events
```

Edit one amount in the JSONL on camera (one keystroke: 1200 → 12), then:

```bash
ledger verify --path demo-events.jsonl
# TAMPERED — hash mismatch at index 2 ... (record was mutated)
```

Then the deeper attack — show `ledger anchor` output, wipe and regenerate
the whole file, and run:

```bash
ledger verify --path demo-events.jsonl --anchors anchors.jsonl
# OK — chain intact ...  ANCHOR FAILURE — ... history was REWRITTEN
```

**[VO]**
> Auditors should assume tampering. Change one number in the ledger —
> one keystroke — and verification names the exact record.
>
> A smarter attacker rewrites the *entire* history into a consistent
> forgery. The chain alone can't see that — so we anchor: a signed
> fingerprint of the chain, stored off the box. The forgery passes the
> naive check and fails the anchor. We tell you exactly which attacks
> each layer stops. That's the product.

---

## SCENE 5 — The honesty line + close (3:25–4:00)

**[SCREEN]** Scroll a service README's **Enforced vs. Declared** table
(sealed-ledger's is the best). Then the board pack
(`integration/demo/out/board-pack/board-pack.html`) — hover the
conformance rate and its printed source query. End card:
*"Force Field Protocol · FIELD Platform · Spin State Labs — Humans
organize; AI operates."* with repo path.

**[VO]**
> Every service in this platform ships a table like this: what is
> enforced in code, with the adversarial test that proves it — and what
> is still only declared. A governance product that overclaims has
> already failed.
>
> It ends at the board: a quarterly pack where every number prints the
> query it came from. No number without a source.
>
> Twelve governance systems, a dashboard, one hundred sixty-eight tests,
> one honest rule. The FIELD Platform, from Spin State Labs. Humans
> organize; AI operates.

---

## 60-second cut (social/teaser)

| Time | Content |
|---|---|
| 0:00–0:08 | Title card + manifest scroll. VO: "A policy that declares what an agent may do is not a control." |
| 0:08–0:30 | run_demo.sh: the ESCALATE and BLOCK callouts only. VO: the fifth-invoice and transfer-funds lines from Scene 2. |
| 0:30–0:45 | Console: harness BLOCK + kill button. VO: "The console holds no authority of its own — every button is ledgered." |
| 0:45–0:55 | Tamper → `TAMPERED at index 2`. VO: "Change one number; the ledger names the record." |
| 0:55–1:00 | End card. VO: "Declared versus enforced. FIELD Platform." |

## Recording notes

- Terminal: 120×32, dark background, no transparency; hide personal paths
  from the prompt (`PS1='field-platform $ '`).
- The demo data is synthetic and labeled as such on screen — leave those
  labels visible; they're part of the honesty story.
- Do not speed up the kill drill or the demo run — real timing *is* the
  claim. Speeding up boot waits is fine (label "sped up").
- If a take glitches, re-run the demo rather than editing output — every
  frame should be reproducible by an evaluator with the repo.
