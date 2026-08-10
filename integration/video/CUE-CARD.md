# Scene 4 cue card — "Try to cheat it"

**Before recording:** `bash integration/video/stage_scene4.sh`
(safe to re-run between takes — it rebuilds everything).
Then: `cd integration/video/scene4`

Type only what's in the boxes. Expected output shown beneath each.

---

## Beat A — the genuine chain verifies (10 s)

```bash
ledger verify --path events.jsonl --anchors anchors.jsonl --pubkey keys/anchor-public.pem
```

> `OK — chain intact over 5 events`
> `OK — 1 anchor(s) hold (1 signature(s) verified)`

---

## Beat B — one keystroke of tampering (15 s)

Open the on-camera copy:

```bash
nano tamper-me.jsonl        # or your editor of choice
```

On line 1, change `"amount":1200` → `"amount":12` (the JSONL is compact —
no space after the colon; delete two zeros and that's the whole edit).
Save. Then:

```bash
ledger verify --path tamper-me.jsonl
```

> `TAMPERED — hash mismatch at index 0: stored … != recomputed … (record was mutated)`

*(VO point: the ledger names the exact record.)*

---

## Beat C — the smart attacker (20 s)

The staged `forged-events.jsonl` is a **complete rewrite**: every hash
recomputed, the `conformance.block [D.scope]` refusal and the `kill.agent`
event replaced with routine allows. Optionally show the diff first:

```bash
diff <(ledger verify --path events.jsonl; grep -o '"event_type":"[^"]*"' events.jsonl) \
     <(ledger verify --path forged-events.jsonl; grep -o '"event_type":"[^"]*"' forged-events.jsonl)
```

The two checks, in order — this is the money shot:

```bash
ledger verify --path forged-events.jsonl
```

> `OK — chain intact over 5 events`   ← the naive check is fooled

```bash
ledger verify --path forged-events.jsonl --anchors anchors.jsonl --pubkey keys/anchor-public.pem
```

> `OK — chain intact over 5 events`
> `ANCHOR FAILURE — … history was REWRITTEN …`

*(VO point: the anchor — a signed fingerprint stored off the box — catches
what the chain alone cannot. One small JSON record; publishing it to a
public chain is the same idea with a harder witness.)*

---

## Retake / safety notes

- `events.jsonl` stays pristine; only ever edit `tamper-me.jsonl`.
  Re-run the stage script to reset everything.
- `scene4/` is gitignored (it contains a regenerated demo private key and
  mutable takes). The committed assets are this card + the stage script.
- Hashes differ every staging run — expected; the *behavior* is identical.
