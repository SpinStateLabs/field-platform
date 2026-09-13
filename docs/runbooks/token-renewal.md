# Token renewal: `tools/renew_token.py`

Written 2026-09-12 for Don's request "renew the token automatically before it
expires", and revised the same night (tool version 1.1) after an adversarial
review found three defects in 1.0 that could undo a human's revocation or
revoke the token vt was using, plus guards no test pinned. Revised again on
2026-09-13 (tool version 1.2): the relay of the verify command's output could
print part of the secret or of a token id (review finding E6), and the Windows
install for the ssl agents was written, with their verifier
`tools/ssl-verify-token.ps1`, and tested against the harness (§5). Revised a
third time on 2026-09-13 (tool version 1.3) after a re-verification: a mint
answer naming one of the agent's earlier tokens, or a uuid never issued, was
still trusted; a changed token lifetime was not compared; and the shim could
hand the verifier the real token file in place of a missing one (§6.3).
Revised a fourth time on 2026-09-13 (tool version 1.4) after a final
re-verification: a mint answer whose whole body had been replaced by
another token's row (another grant, or another agent's token) was abandoned
without a sweep, so the token the mint really created stayed active with no
journal naming it (§6.2). Revised a fifth time on 2026-09-13 (tool version
1.5) after a re-verification of 1.4: when that sweep could not list the
tokens and the revoke of the named token failed or was refused too, the
journal left behind did not record the unfinished sweep, and later runs
revoked or refused that token without sweeping again (§6.1). The first
target is `volatility-trader` (vt) on the GB10; the ssl agents on
rog-command are the second. Neither is installed.

Nothing in this runbook has been run on the GB10 or registered in Task
Scheduler. Section §6 lists what was verified, and where, including what the
mutation runs did and did not confirm. Commands marked **Don** change
persistent state (crontab, scheduled tasks) or write to a real agent's
authority, so they need Don's go.

---

## 1. What it guarantees, and what it does not

### Guarantees

Each guarantee below is pinned by tests in `tools/tests/test_renew_token.py`,
run against the real services with the estate's shared secret and a DOA roster
armed. §6 gives the full-module mutation result: which guards were removed one
at a time, and whether the whole module then failed.

1. **The old token is revoked only after the new one is proven.** The proof is
   `--verify-cmd`, run *after* the new id is in the store. For vt that means
   `verify_vt_field.py full`, going through vt's own `config.py` and
   `field_client.py`. A renewal without `--verify-cmd`, or with one that does
   not contain `{new_token}`, is refused. After the command exits 0, the tool
   itself checks only two more things before revoking the old token: the store
   still holds the new id, and neither token was revoked while the verifier ran.
   Everything else is only as strong as the verifier: a command that receives
   `{new_token}` and ignores it would still be accepted.
2. **The grant is carried forward exactly.** The new token has the same
   `agent_id`, the same `granted_by` and the same scope list in the same order,
   the lifetime the tool asked for (`expires_at - issued_at` within 5 seconds
   of `ttl_seconds`), and is active. The tool compares both the mint response
   and a fresh `GET` of the new token. If either differs, the new token is
   never swapped in. The lifetime is compared because the authority computes
   `expires_at` from `ttl_seconds` exactly and refuses a TTL over the roster
   maximum (403) instead of clamping it: any other lifetime means the request
   or the answer was altered on the way (1.2 swapped in a 90-second token and
   revoked the 30-day one).
3. **Only the token value changes in the store.** Every other byte of
   `~/vt/secrets.env` stays the same, including the `ANTHROPIC_API_KEY` line and
   whether the file ends with a newline. The tool never decodes, prints or
   rewrites any other line. The write is a temp file in the same directory,
   then fsync, `os.replace` and a directory fsync. The file mode is kept. The
   file is read back, and if it does not match, the original bytes are
   written back.
4. **A failed proof undoes the swap, unless undoing it would do harm.** If the
   verify command exits non-zero, times out (120 s, and its whole process tree
   is killed) or cannot start, the tool restores the store byte for byte,
   revokes the new token, leaves the old token alone and ledgers
   `token.renewal_failed`. Three exceptions, each ending in exit 1 with the
   journal kept:
   - the old token is no longer active (expired, not found, or revoked before
     the renewal under `--renew-revoked`): it is not put back, and the new
     token stays in the store unrevoked;
   - the restore write fails: the store still holds the new token, so the new
     token is **not** revoked (the log says `store STILL HOLDS <new>`);
   - either token cannot be read after verification: nothing is restored or
     revoked, and the next run reads them again.
5. **It never overlaps a vt run, or another renewal of the same store.** The
   tool always takes the store's own lock, `~/vt/.secrets.env.renew-lock`, and
   also `--lock-file ~/vt/.lock`, the lock `run.sh` holds. Both are
   non-blocking and held until the run ends, verification included. If either
   is held, the tool logs `skipped: lock held (<path>)` and exits 3, having
   written nothing. A run **without** `--lock-file` still excludes other
   renewals, but it does not take `~/vt/.lock`, so it could overlap a vt run:
   always pass `--lock-file` (§4 gives the hand-run command).
6. **A crash at any point is reconciled by the next run.** A journal in
   `~/vt/.renew-token/` records the intent before the mint, the new id before
   the swap, and phase `verified` before the old token is revoked. On the next
   run:
   - a lost mint response (the authority minted, the tool never saw the id)
     is swept up and revoked;
   - a token minted but never swapped in is revoked, and then the agent's
     tokens are swept again for another token that mint created, with the
     journal's own snapshot and mint window and leaving that id out (the run
     that wrote the journal may have left its sweep unfinished); a sweep that
     cannot list the tokens keeps the journal for the next run. A journal
     token of another agent is swept for the same way, then refused (rc 2).
     If the id answers 404 on every read and is absent from the agent's token
     list too (a mint answer named an id that was never issued), the agent's
     tokens are swept instead;
   - a token already swapped in has both tokens read again, then goes back
     through verification;
   - a renewal whose verification had passed only retries the old token's
     revoke and the ledger. It is never verified again and never rolled back.

   **A mint answer is trusted only when it names a new token.** Before the
   mint the tool lists the agent's tokens; the current token is always counted
   in that snapshot. A `201` whose `token_id` is missing, not a uuid, in the
   snapshot (vt's current token, or any other token vt already had), or never
   issued (404 on every read and absent from a fresh token list) is a lost
   answer: nothing is revoked by that id, nothing is swapped, the intent
   journal is kept and the agent's tokens are swept for the token the mint
   really created. If the fresh `GET` of a new id shows another grant or
   lifetime than the answer described, or answers 404 for an id the token list
   does carry, that id is revoked where it can be (it did not exist before the
   mint), the tokens are swept as well, and the journal is kept: the intent
   once that id is confirmed revoked, otherwise the journal naming it. If the
   answer itself shows another grant, lifetime or row, it may be another
   token's whole row put in place of the real one (another agent's token, for
   one): the tokens are swept first, leaving out the id it names, and only
   then is that id revoked, or refused with rc 2 when it belongs to another
   agent. The journal is then cleared once that id is confirmed revoked,
   unless the sweep revoked a token or could not list them: then the intent
   is kept. When that id's revoke is not confirmed, on either path, the
   journal naming it is kept (`journal: kept for the next run`), and the next
   run revokes that id and then sweeps the mint's window again before it
   clears the journal; a refused id's journal is swept for again by every
   later run before it refuses (the bullet above). 1.3 revoked or refused
   that id without a sweep, and the token really minted stayed active with no
   journal naming it. 1.4 swept only in the run that abandoned the mint: when
   that sweep could not list the tokens and the revoke failed, the next run
   revoked the named token, cleared the journal and renewed (rc 0) with the
   real mint still active. The only token of the snapshot a renewal ever
   revokes is the current one, after verification.
   1.2 trusted any well-formed id other than the current token's: an answer
   naming an earlier same-grant token swapped that token in and revoked the
   current one (rc 0); one naming an unrelated token revoked it; a never-issued
   uuid left a journal every later run stopped on. A journal whose new token is
   in its own snapshot is refused as invalid.

   The sweep only touches a token that meets all of these: absent from the
   token list snapshotted before the mint, carrying the exact grant, not the
   store's token or the journal's old token, not already revoked, of this
   agent, and issued between 2 minutes before and 2.5 minutes after the
   interrupted mint began.
7. **It never undoes a revocation it can see.**
   - A revoked current token is refused (exit 2) unless `--renew-revoked` is
     given.
   - If the renewal's new token is revoked or expired before the renewal
     finished, whether during verification or while a crashed run's journal
     waited, the tool refuses (exit 2): nothing restored, nothing revoked,
     journal kept. `--renew-revoked` does not bypass this.
   - If the old token is revoked by someone else while the renewal is in
     flight, the new token is revoked too, and the tool exits 2.

   Limit: in phase `verified` the tool treats a revoked old token as its own
   revoke (possibly with a lost answer), because it cannot tell the two apart.
8. **A revoke is counted only when the authority confirms it.** The authority
   must answer `revoked: true` for exactly the token asked for. A token it
   cannot find, a read that fails, a read-back of another token, or a `200`
   that does not say `revoked: true` for that id keeps the journal, so the next
   run tries again.
9. **Secrets.** `x-field-auth` comes from `FIELD_SHARED_SECRET` or
   `--secret-file`, following estate_probe's rules:
   - a value with whitespace, control or non-ASCII characters is refused, and
     never printed;
   - stdout and stderr are redacted, including the verify command's relayed
     output and the escaped form a traceback would print;
   - the verify command's output is relayed from its last 64 KiB, starting at
     a complete line: a line the window cuts is dropped whole, so neither the
     secret nor a token id is printed in part (1.1 printed the rest of a value
     the cut went through). In what is relayed, every run of 8 or more
     characters of the secret, or of a full token id past its 8-character
     prefix, is masked, also when the verifier's own output broke the value
     across lines (PowerShell wraps an error record at 120 columns). A
     fragment of 7 characters or fewer is not masked, and neither is a value
     the verifier altered in any other way;
   - redirects are never followed, and `HTTP_PROXY`-style environment proxies
     are ignored;
   - cleartext to a public host is refused;
   - response bodies are never printed (only a status and a clause id).

   Token ids appear only as 8-character prefixes in the log.

### It does not

- **Mint where the estate refuses.** This fails loudly: exit 1, the store is
  untouched and the failure is ledgered. Refusals include:
  - vt is killed or retired (409);
  - the DOA roster is armed and "Don Hagell" is not an active row on it
    (403 `D.grantor`);
  - `--ttl-days 30` is above the roster's `max_ttl_days` (403 `D.grantor`);
  - vt's manifest does not resolve (422 `D.scope`);
  - the roster is unreadable (503).

  In particular, **it cannot renew a token whose grantor has been removed from
  an armed roster.** vt keeps its current token until that token expires, and
  then halts `D.expired` as before.
- **Alert anyone.** The only signals are the exit status, the log and the
  ledger. If nobody reads them, seven days of failures end in vt halting at
  expiry. See §4.1 for a check to run.
- **Prove more than its verifier proves.** `verify_vt_field.py full` checks
  the following at renewal time:
  - heartbeat: active, not killed;
  - an in-scope ALLOW, enforced and not shadowed;
  - an out-of-scope `D.scope` BLOCK;
  - governor state `OK` with `limit_cents 500`;
  - both conformance events ledgered.

  It is not a trading run. Each verification adds 2 conformance events to
  vt's ledger. The pinned verifier loads `VT_FIELD_TOKEN_ID` once, at its
  start; a store changed while it runs is caught by the tool's re-read
  (guarantee 1), not by the verifier.
- **Authenticate the grantor.** `granted_by` is carried forward as a string.
  The roster matches strings, not people.
- **Protect against the same Unix user.** Anyone who can edit
  `~/vt-renewal/` can also edit `SHA256SUMS`. The hash check catches
  accidental change (a paste error, a deploy) but not an attacker.
- **Guarantee its own ledger events.** A failed `token.renewed` or
  `token.renewal_failed` append is reported in the log and does not change the
  exit status. The authority's own `delegation.mint` and `delegation.revoke`
  events are fail-closed: the authority refuses to mint or revoke if it
  cannot ledger. Those events are the record that does not depend on this tool.
  A run that dies after appending `token.renewed` and before clearing its
  journal appends it again on the next run.
- **Exclude a same-grant concurrent mint.** If someone mints a token with the
  exact same grant during the seconds of one of the tool's own mints whose
  answer was lost or not trusted, or whose token never reached the store, and
  that token is not in the store, the sweep treats it as the orphan and
  revokes it, also in a later run's recovery of that mint's journal. And if
  something between the tool and the authority rewrites
  the mint answer (its id, or its whole body) to name a token someone else
  minted for vt during those seconds (after the snapshot): with another grant
  or lifetime, that token is revoked and the real mint swept; with the exact
  grant and lifetime, it is indistinguishable from the tool's own mint, so it
  is swapped in and proven, and the token the mint really created stays
  active, unjournaled, until it expires. An answer naming another agent's
  token sweeps the real mint and then refuses (rc 2); every later run sweeps
  that mint's window again and refuses on that journal until a human
  reconciles it (§4.2). A hop that alters the
  request's grant AND puts another token's row in the answer leaves the token
  really minted, with a grant nobody asked for, active and unjournaled: no
  sweep matches that grant, and only listing vt's tokens finds it (§4.2). A
  token vt had before the mint is never touched.
- **Tell a human's revoke of the old token by hand from its own**, once the
  journal says `verified` (guarantee 7). Never revoke either token by hand while
  a journal is pending (§4.2).
- **Record the owner of a journal.** A journal found under the store's lock is
  treated as left by a dead run. That is sound because every renewal of the
  store takes that lock whatever its flags; there is no pid or boot-id check.

---

## 2. How a run reads

Exit status: `0` renewed, not due, or `--check`; `1` failed; `2` refused
(a human must look); `3` lock held.

A not-due day, which is most days (GETs only, no writes). The ids and dates below are illustrative:

```
renew_token 1.5 2026-09-13T18:35:01Z agent=volatility-trader base=http://127.0.0.1:18080 store=env-file /home/spinner/vt/secrets.env key VT_FIELD_TOKEN_ID
store: VT_FIELD_TOKEN_ID holds token 1a2b3c4d
lock: acquired /home/spinner/vt/.secrets.env.renew-lock and /home/spinner/vt/.lock
journal: none
token: 1a2b3c4d agent=volatility-trader granted_by='Don Hagell' scope=4 entries expires 2026-10-12T23:30:00Z
not due: 29 days left (expires 2026-10-12T23:30:00Z; renewal window 7 days)
```

A renewal. This is an excerpt of a real run of version 1.3 against the harness,
with the canary agent and `estate_probe canary` standing in for vt and its
verifier. The ids, paths and agent differ on the GB10, and it was a Windows
run, so the GB10 shows `mode 0o600`. The shape is the same:

```
decide: due (expires within 7 days: 1.0 days left)
ttl: 86400 s = 1 days (current lifetime 1.00 days)
journal: intent recorded (.../renewal/state/renew-canary-gb10-be856b75a0....json)
mint: HTTP 201 new token b4b60dc2; journal records it before the swap
confirm: b4b60dc2 persisted with the same agent, grantor and 3 scope entries in the same order and the requested 86400 s lifetime, expires 2026-09-14T08:57:07Z
swap: VT_FIELD_TOKEN_ID 467a2773 -> b4b60dc2 (atomic replace; 202 other bytes identical; mode 0o666)
verify: running python.exe (timeout 120 s)
  verify| canary C0 - canary-gb10
  verify|   [PASS] heartbeat 200 killed=false
  ...
verify: rc=0
tokens: new b4b60dc2 active until 2026-09-14T08:57:07Z; old 467a2773 active until 2026-09-14T08:57:06Z
journal: verified; revoking the old token
revoke-old: 467a2773 revoked
ledger: token.renewed appended
journal: cleared
result: renewed 467a2773 -> b4b60dc2, expires 2026-09-14T08:57:07Z
```

A mint answer that names a token vt already had (1.3, real output; the
proxy rewrote the answer's id):

```
mint: FAILED (HTTP 201 without a new token id: missing, not a uuid, a token that existed before the mint (the current token's own id among them), or an id never issued); nothing swapped and nothing revoked by that id
sweep: orphan 57cdef6f revoked
ledger: token.renewal_failed appended
journal: intent kept, so the next run sweeps again for a token persisted late
result: FAILED at mint; store and old token 949d33ed untouched
```

A mint answer whose whole body is another token's row, here a token minted
for the agent during the mint with another scope (1.4, real output against
the harness; the proxy replaced the answer). The token the mint really
created is swept before the named token is revoked:

```
mint: HTTP 201 new token 21d529cc; journal records it before the swap
abandon: mint response differs from the current grant (scope)
sweep: orphan 999f6d67 revoked
revoke-new: 21d529cc revoked
ledger: token.renewal_failed appended
journal: intent kept, so the next run sweeps again
result: FAILED (mint_mismatch); store holds 2ba5a88c (the old token); old token 2ba5a88c not revoked
```

When that sweep cannot list the tokens and the revoke of the named token
fails too, the run keeps the journal naming it, and the next run revokes it
and sweeps the mint's window again before it renews (1.5, real output
against the harness; the proxy answered 500 to the token list and to the
revoke in the first run only):

```
abandon: mint response differs from the current grant (scope)
sweep: could not list tokens (HTTP 500)
revoke-new: 631b15bd revoke FAILED (HTTP 500)
ledger: token.renewal_failed appended
journal: kept for the next run
result: FAILED (mint_mismatch); store holds 7e7cc2d9 (the old token); old token 7e7cc2d9 not revoked
```

```
recovery: token 631b15bd was minted but never reached the store; revoking it
recovery: 631b15bd revoked
recovery: sweeping for another token that mint created (its run may not have finished a sweep)
sweep: orphan 0827a60d revoked
ledger: token.renewal_failed appended
journal: cleared
```

A failed verification ends like this (again real output):

```
verify: rc=1
tokens: new d75db11f active until 2026-09-14T02:41:14Z; old caa9d665 active until 2026-09-14T02:41:13Z
restore: store holds caa9d665 again (202 other bytes identical; mode 0o666); byte-for-byte identical to before the renewal: True
revoke-new: d75db11f revoked
ledger: token.renewal_failed appended
journal: cleared
result: FAILED at verification (rc=1); store holds caa9d665 (the old token)
```

The `result:` line of a failure is built from a fresh read of the store, so it
says which token the store really holds: `(the old token)`, `STILL HOLDS
<id> (the new token)`, `(neither the old nor the new token)`, or `CANNOT BE
READ`.

**Files the tool writes.**
- The store, only on a renewal, and a temp file beside it, which lasts
  milliseconds and is removed by the next run if a crash leaves one.
- The store's lock file, `~/vt/.secrets.env.renew-lock`: empty, created on
  the first run and left in place.
- The journal, `~/vt/.renew-token/renew-volatility-trader-<hash>.json`: mode
  0600, directory 0700. The journal holds token ids and grant strings, never a
  secret, and exists only while a renewal is in flight or was interrupted.

---

## 3. Install for vt on the GB10

Run everything in a shell on the GB10 as `spinner`. Each step lists **Expect**
and **STOP if**.

- Do not start within 15 minutes of a vt slot. Cron is in local time
  (America/Toronto), so the slots are 00:05, 04:05, 08:05, 12:05, 16:05 and
  20:05, and a run takes about 11 to 12 minutes.
- Never `cat`, `source` or `env` anything that touches `~/vt/secrets.env`
  (REPAIR-PLAN §0.1).

**3.0 Preconditions**

```sh
umask 077; set +x; date; timedatectl show -p Timezone --value
R=$(cat ~/vt-repair/CURRENT) && ls -l "$R/verify_vt_field.py"
grep -nE '^(VT_FIELD_TOKEN_ID|FIELD_[A-Z]+_URL)=' ~/vt/secrets.env
crontab -l | grep 'vt-runner'
```

Expect all of the following:
- timezone `America/Toronto`;
- the repair directory's `verify_vt_field.py` exists;
- one `VT_FIELD_TOKEN_ID=` line and the four `http://127.0.0.1:18080/...` URL
  lines;
- the `5 */4 * * * ... --shadow ... # vt-runner` line.

STOP if the repair (REPAIR-PLAN §5.1 `RESULT PASS`) has not been completed:
the tool would faithfully renew a token vt cannot use. Also STOP if the
key's line count is not exactly 1.

**3.1 Directory**

```sh
mkdir -p ~/vt-renewal && chmod 700 ~/vt-renewal && ls -ld ~/vt-renewal
```

Expect `drwx------`.

**3.2 The tool.** Copy it from the reviewed build on rog-command, from
PowerShell there:

```powershell
scp "C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform\tools\renew_token.py" gx10:vt-renewal/renew_token.py
```

Then on the GB10:

```sh
chmod 600 ~/vt-renewal/renew_token.py && sha256sum ~/vt-renewal/renew_token.py && python3 --version
```

Expect `3a0683588a5a90bd7b7bb6fac9ab2798907af5772c8be058f4d1b5c436d3df29  /home/spinner/vt-renewal/renew_token.py` and `Python 3.12.x`. The tool was syntax-checked for 3.12 and executed on 3.14 only.
The pins are for the files' LF bytes: `.gitattributes` checks `tools/renew_token.py` and
`tools/*.ps1` out with LF whatever `core.autocrlf` says, and a test checks that. A copy
with CRLF line endings (an editor, a zip, a checkout from before that rule) hashes differently.
STOP if the hash differs: the file is not the build this runbook was
written and tested against.

**3.3 A stable copy of vt's verifier.** The repair directory is a working
area, so the verifier is copied out of it.

```sh
install -m 600 "$R/verify_vt_field.py" ~/vt-renewal/verify_vt_field.py && sha256sum ~/vt-renewal/verify_vt_field.py
```

Expect `8f75f1bb6a6e77301b599474d6227f44a5251b0c1286c43dd0579aefaf5f0c17  /home/spinner/vt-renewal/verify_vt_field.py` (the REPAIR-PLAN §1.8 pin).
STOP if the hash differs.

**3.4 The verify wrapper.** This wrapper matters. It starts the verifier
from an **empty environment** and loads only the `FIELD_*_URL`,
`VT_FIELD_TOKEN_ID` and `FIELD_SHARED_SECRET` lines of the *swapped*
`secrets.env`, exactly as REPAIR-PLAN §1.8 does. It refuses to run an
unpinned verifier (exit 97).

```sh
cat > ~/vt-renewal/verify-vt.sh <<'SH'
#!/bin/bash
# verify-vt.sh <new-token-id>: prove a renewed vt token through vt's OWN client.
# renew_token.py calls this AFTER it has written the new id into ~/vt/secrets.env.
# It starts from an EMPTY environment and loads only the FIELD_*_URL,
# VT_FIELD_TOKEN_ID and FIELD_SHARED_SECRET lines (REPAIR-PLAN 1.8), so
# ANTHROPIC_API_KEY never enters the verifier. Exit 97: the verifier is not the pinned copy.
set -u
NEW="${1:?usage: verify-vt.sh <new-token-id>}"
DIR="$HOME/vt-renewal"
PINNED="8f75f1bb6a6e77301b599474d6227f44a5251b0c1286c43dd0579aefaf5f0c17"
GOT=$(sha256sum "$DIR/verify_vt_field.py" | cut -d' ' -f1)
if [ "$GOT" != "$PINNED" ]; then
  echo "verify-vt: verify_vt_field.py sha256 $GOT is not the pinned $PINNED"
  exit 97
fi
exec env -i HOME="$HOME" PATH=/usr/bin:/bin bash --noprofile --norc -c 'set -a; . <(grep -E "^(FIELD_[A-Z]+_URL|VT_FIELD_TOKEN_ID|FIELD_SHARED_SECRET)=" "$HOME/vt/secrets.env"); set +a; exec python3 -B "$1" full "$2"' _ "$DIR/verify_vt_field.py" "$NEW"
SH
chmod 700 ~/vt-renewal/verify-vt.sh && sha256sum ~/vt-renewal/verify-vt.sh
```

Expect `98117016e8dc65ad59f437173dcda93656a0fdd04ee0de7df601b27d8c7bd50f  /home/spinner/vt-renewal/verify-vt.sh`.
STOP if it differs (paste damage): delete the file and paste again.

**3.5 Pin all three files**

```sh
cd ~/vt-renewal && printf '%s  %s\n' \
  3a0683588a5a90bd7b7bb6fac9ab2798907af5772c8be058f4d1b5c436d3df29 renew_token.py \
  8f75f1bb6a6e77301b599474d6227f44a5251b0c1286c43dd0579aefaf5f0c17 verify_vt_field.py \
  98117016e8dc65ad59f437173dcda93656a0fdd04ee0de7df601b27d8c7bd50f verify-vt.sh > SHA256SUMS && sha256sum -c SHA256SUMS
```

Expect `renew_token.py: OK`, `verify_vt_field.py: OK`, `verify-vt.sh: OK`.

**3.6 Dry runs.** These make GETs only and write nothing but the log (and,
on the second command, the empty store lock file).

```sh
python3 -B ~/vt-renewal/renew_token.py --agent volatility-trader --base http://127.0.0.1:18080 --env-file ~/vt/secrets.env --env-key VT_FIELD_TOKEN_ID --check; echo "rc=$?"
```

Expect `token: <prefix> agent=volatility-trader granted_by='Don Hagell' scope=4 entries expires <about 30 days after the manual renewal>`, then `check: not due: N days left` and `rc=0`.
STOP on `refused:` or `rc=1`. Read §4 first.

Then run the exact cron command from the minimal environment cron gives it:

```sh
env -i HOME="$HOME" PATH=/usr/bin:/bin SHELL=/bin/sh LOGNAME="$LOGNAME" /bin/sh -c 'cd /home/spinner/vt-renewal && /usr/bin/sha256sum --quiet -c SHA256SUMS >> /home/spinner/vt/logs/token-renewal.log 2>&1 && /usr/bin/python3 -B /home/spinner/vt-renewal/renew_token.py --agent volatility-trader --base http://127.0.0.1:18080 --env-file /home/spinner/vt/secrets.env --env-key VT_FIELD_TOKEN_ID --lock-file /home/spinner/vt/.lock --ttl-days 30 --verify-cmd "/home/spinner/vt-renewal/verify-vt.sh {new_token}" >> /home/spinner/vt/logs/token-renewal.log 2>&1'; echo "rc=$?"; tail -8 ~/vt/logs/token-renewal.log
```

Expect `rc=0` and a log ending `lock: acquired /home/spinner/vt/.secrets.env.renew-lock and /home/spinner/vt/.lock`, `journal: none`, `token: ...` and `not due: N days left (...)`.

**3.7 Install the daily cron line (Don).** It runs at 14:35 local time,
chosen for three reasons:
- it is 2 h 18 min after the 12:05 run ends and 1 h 30 min before the 16:05 run;
- it is outside the 02:00 to 03:00 DST changeover;
- it falls in Don's working day, so a failure is seen the same day.

A renewal takes seconds, and at most about 3 minutes if verification hits its
120 s timeout.

```sh
crontab -l > ~/vt-renewal/crontab.before && { cat ~/vt-renewal/crontab.before; echo '35 14 * * * cd /home/spinner/vt-renewal && /usr/bin/sha256sum --quiet -c SHA256SUMS >> /home/spinner/vt/logs/token-renewal.log 2>&1 && /usr/bin/python3 -B /home/spinner/vt-renewal/renew_token.py --agent volatility-trader --base http://127.0.0.1:18080 --env-file /home/spinner/vt/secrets.env --env-key VT_FIELD_TOKEN_ID --lock-file /home/spinner/vt/.lock --ttl-days 30 --verify-cmd "/home/spinner/vt-renewal/verify-vt.sh {new_token}" >> /home/spinner/vt/logs/token-renewal.log 2>&1 # vt-token-renewal'; } | crontab -
crontab -l | grep -c '# vt-token-renewal'; crontab -l | grep 'vt-runner' | cmp -s - <(grep 'vt-runner' ~/vt-renewal/crontab.before) && echo "vt-runner line unchanged"
```

Expect `1` and `vt-runner line unchanged`.

Two notes on the line:
- `--ttl-days 30` matches tonight's manual grant and the DOA ceiling in
  REPAIR-PLAN §3.1.
- The state directory defaults to `~/vt/.renew-token/`, beside the store. A
  manual run with the same flags therefore finds any journal the cron left.

**When the first automatic renewal happens.** The first 14:35 run with
7 days or less left does it. Tonight's token expires 30 days after its mint
(about 2026-10-12), so that is about 2026-10-06. The `--check` output in 3.6
gives the exact number of days.

**3.8 Optional: prove one renewal now (Don: a real-agent write).** Without
this step, the first live renewal is the unobserved 2026-10-06 run. The
step runs the cron command once with `--renew-within-days 30` added, which
forces the renewal. It does the following:
- mints a new vt token;
- verifies it through vt's client, which adds 2 conformance ledger events;
- revokes tonight's manually minted token.

Rule 7 allows it as a scheduled token renewal. Record it in STATE.md as
"executed by a Claude session on Don's 2026-09-12 instruction".

Run it outside the slot windows, with the same `env -i ... /bin/sh -c '...'`
command as 3.6 plus ` --renew-within-days 30` before the `>>`. Expect `rc=0` and a log ending
`journal: verified; revoking the old token`, `revoke-old: <old> revoked`, `ledger: token.renewed appended`, `journal: cleared` and
`result: renewed <old> -> <new>, expires <30 days out>`. For this one-off run
only, expect a `note:` line saying the 30-day lifetime is inside the 30-day
renewal window. Then confirm on the ledger:

```sh
curl -s 'http://127.0.0.1:18080/ledger/events?agent_id=volatility-trader&event_type=token.renewed' | jq -c '.[-1] | {ts, payload}'
curl -s 'http://127.0.0.1:18080/delegation/tokens?agent_id=volatility-trader' | jq -r '.[] | [.token_id[0:8], .granted_by, .expires_at, "revoked=\(.revoked)"] | @tsv'
```

The next scheduled vt run must then meet REPAIR-PLAN §5.5's "repaired"
criteria, as it did after the manual renewal.

**3.9 When A2 (the perimeter secret) arms.** Two changes are needed, both
before A2 arms. The `curl` lines above then need the header (REPAIR-PLAN §4.3).
1. vt's `secrets.env` needs its `FIELD_SHARED_SECRET` line (REPAIR-PLAN §4.2).
   The wrapper already loads it.
2. The cron line needs `--secret-file /home/spinner/.field-local/estate-secret`.
   That path is UNVERIFIED until A2 creates the file. Without it, every run logs
   `token: GET <prefix> failed (HTTP 401) (x-field-auth missing or wrong); nothing written`
   and exits 1.

**3.10 Uninstall.** This removes nothing from the estate. A renewal that
already happened leaves a valid token in place.

```sh
crontab -l | grep -v '# vt-token-renewal' | crontab - && crontab -l | grep -c vt-token-renewal; ls ~/vt/.renew-token/ 2>/dev/null
```

Expect `0`. If the journal directory holds a `.json` file, a renewal was
interrupted. Reconcile it (§4.2) before deleting `~/vt-renewal`,
`~/vt/.renew-token` and `~/vt/.secrets.env.renew-lock`.

---

## 4. Reading a failure

Start with `tail -40 ~/vt/logs/token-renewal.log`. The last `result:`,
`refused:` or `skipped:` line says how the run ended. The lines above it say
at which step.

**Running it by hand.** Always with `--lock-file`, so it cannot overlap a vt
run, and with the cron line's other flags, so it finds the cron's journal:

```sh
cd /home/spinner/vt-renewal && /usr/bin/sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -B /home/spinner/vt-renewal/renew_token.py --agent volatility-trader --base http://127.0.0.1:18080 --env-file /home/spinner/vt/secrets.env --env-key VT_FIELD_TOKEN_ID --lock-file /home/spinner/vt/.lock --ttl-days 30 --verify-cmd "/home/spinner/vt-renewal/verify-vt.sh {new_token}" 2>&1 | tee -a /home/spinner/vt/logs/token-renewal.log; echo "rc=${PIPESTATUS[0]}"
```

Add `--renew-revoked` only where the table says so, and only on Don's decision.
Add `--secret-file ...` once A2 is armed (3.9).

| Log line | Meaning | What to do |
|---|---|---|
| `skipped: lock held (/home/spinner/vt/.lock)`, rc 3 | A vt run (or something holding its lock) was in progress. Nothing was written. | Nothing, if it happens once: tomorrow retries, and the 7-day window allows about 6 attempts. If it repeats, look for a stuck run: `pgrep -fa 'runner.py'`. |
| `skipped: lock held (/home/spinner/vt/.secrets.env.renew-lock)`, rc 3 | Another renewal of this store (the cron's, or a hand run) was in progress. | Wait for it: `pgrep -fa renew_token.py`. |
| `refused: VT_FIELD_TOKEN_ID must be defined exactly once ...` or `... is not a lowercase uuid` | The store line is missing, duplicated, quoted, CRLF or malformed. The tool touched nothing. | Fix the line with REPAIR-PLAN's `setenv.py`, not by hand. If a journal is pending, §4.2 first. |
| `refused: token X belongs to agent '...'` | The store holds another agent's token. | A human must find out how. Nothing was written. |
| `refused: token X is not known to the delegation authority` | Estate data loss, or the wrong estate. | Do not re-mint blind: the grant could not be read. Escalate to Don. |
| `refused: token X is REVOKED` | Someone revoked vt's current token. | Find out why. Only if Don wants vt re-granted, run the hand command once with `--renew-revoked`. |
| `refused: token X, the renewal's new token, is REVOKED while the renewal was not finished; store STILL HOLDS X ... Old token Y is active until ...` (or `EXPIRED`) | Someone revoked vt's token while a renewal was in flight or waiting in a crashed run's journal. The tool restored nothing: putting Y back would undo the revocation. **Y may still be active.** It repeats every day until a human acts. | Don decides. To keep vt halted: revoke Y if the line says it is active, then delete the journal (§4.2). To re-grant: revoke Y, delete the journal, then run the hand command with `--renew-revoked`. |
| `refused: token Y was revoked during the renewal; ... X is revoked` | Someone revoked vt's old token while the renewal was in flight. The tool revoked the new token too, so vt now holds a revoked token and halts `D.revoked`. | As for `is REVOKED` above. If the line says `NOT confirmed revoked`, the journal is kept and the next run retries. |
| `refused: journal ... records that X passed verification, but VT_FIELD_TOKEN_ID now holds Z` | `secrets.env` was changed after a verified renewal was interrupted. The old token may already be revoked. | §4.2: check all three tokens' state before touching anything. |
| `refused: journal token X belongs to another agent` / `journal ... is not a valid renewal journal (...)` / `unreadable` | The journal was edited or damaged. `(new_token existed before the mint ...)` means it names, as the token to revoke, a token that was in its own pre-mint snapshot; no run of 1.3 or later writes one. | §4.2. |
| `refused: shared secret contains whitespace ...` / `the secret would travel in cleartext` / `--verify-cmd must pass {new_token}` | Secret, base or command misconfiguration. | Fix the cron flags. |
| `token: GET X failed (HTTP 401) (x-field-auth missing or wrong)` | A2 is armed and the cron line lacks the secret, or has the wrong one. | §3.9. |
| `token: GET X failed (transport error URLError)` | The estate or proxy is down. | Tomorrow retries. Check `docker ps` for field-platform containers. |
| `token: malformed response for X (token_id)` | The authority answered with another token's row (the store race below). Nothing written. | Tomorrow retries. |
| `mint: FAILED (HTTP 403 D.grantor)` | The DOA roster is armed and "Don Hagell" is not an active row, lacks vt's 4 scopes, or has `max_ttl_days` < 30. | Don fixes the roster (or lowers `--ttl-days` to its ceiling). Store and old token are untouched. |
| `mint: FAILED (HTTP 422 D.scope)` | The roster is armed and vt's manifest does not resolve, or the scope is outside it. | Check `/data/manifests/volatility-trader.yaml` on the estate. |
| `mint: FAILED (HTTP 409)` | vt is killed or retired. | By design, a renewal never outranks a kill. |
| `mint: FAILED (HTTP 503)` | The roster is set but unreadable. | Fix the roster file. |
| `mint: FAILED (HTTP 502 ...)` / `(transport error ...)` + `sweep:` lines + `journal: intent kept` | The authority may have minted before the answer was lost. The sweep revoked any orphan it found. | Nothing: the next run sweeps again, then renews. |
| `mint: FAILED (HTTP 201 without a new token id ...)` + `sweep:` lines | The mint answer carried no id, a malformed one, the id of **a token vt already had before the mint** (its current token or any other), or an id the authority never issued (then a `confirm: X was never issued ...` line comes first). Nothing was revoked by that id and nothing swapped; the token really minted was swept; the intent journal is kept. | Treat as a security incident if it repeats: something between the tool and the authority rewrites answers. The next run sweeps again, then renews. |
| `mint: not attempted; the agent's tokens could not be listed first` / `journal: cannot write ...; not minting` | The estate or the disk failed before the mint. Nothing minted. | Tomorrow retries; check the disk if it is the journal. |
| `abandon: mint response differs from the current grant (scope)` / `(granted_by)` / `(agent_id)` / `(lifetime)` / `(not active)` / `(malformed ...)` + `sweep:` lines | Something between the tool and the authority altered the request's grant or lifetime (`--ttl-days` asked for one; the token has another), or replaced the answer, possibly with another token's whole row. The tokens were swept first for the token the mint really created, leaving out the named id: `sweep: no orphan token found` when the answer names the real mint, `sweep: orphan X revoked` when it named another token. The named token was then revoked and never swapped in: `journal: cleared`, or `journal: intent kept, so the next run sweeps again` when the sweep revoked a token or could not list them (`sweep: could not list tokens`). If that revoke failed too (`revoke-new: X revoke FAILED`), `journal: kept for the next run`: the next run revokes X and then sweeps again (the `recovery: sweeping ...` row). For `agent_id` the tool refuses to touch another agent's token: `refused: token X does not belong to volatility-trader; refusing to revoke it`, rc 2, after the sweep; the journal still names X, and every later run sweeps again and refuses the same way until §4.2. | Treat as a security incident. After an `agent_id` refusal, reconcile by hand (§4.2), including step 2's unjournaled tokens. |
| `abandon: new token could not be confirmed (scope)` / `(granted_by)` / `(lifetime)` / `(agent_id)` / `(HTTP 404)` + `sweep:` lines | The answer described the requested grant, but the authority's own row for that id shows another, or every read of that id answers 404 while the token list carries it. The id may not be the token this mint created: the tokens were swept for it, and the named token (it did not exist before the mint) was revoked where it could be. Never swapped in. `journal: intent kept, so the next run sweeps again` when that token was confirmed revoked; `journal: kept for the next run` (naming it) when not; for `(agent_id)`, the refusal of the row above. | Treat as a security incident unless it is a one-off 404 (the store race below). The next run sweeps again (intent kept), or revokes the named token and then sweeps again (journal naming it), then renews. |
| `abandon: new token could not be confirmed (...)` (another failed read, `token_id`, `malformed ...`, `not active`) | The fresh read of the new token failed, answered another row, or showed it revoked. Never swapped in. | Nothing, unless the journal is kept: then the next run revokes it. |
| `abandon: the store changed after it was read; not swapping` | `secrets.env` was edited during the renewal. The new token was revoked. | Rerun by hand. |
| `swap: write failed (...); the original bytes are still in place` or `...; original bytes written back and confirmed` | A disk or permission problem. The new token was revoked. | Fix the disk. |
| `swap: ... RESTORING THE ORIGINAL BYTES ALSO FAILED` + `revoke-new: X NOT revoked: the store holds it` (or `cannot be read`) | The store may now hold the new token, or be damaged. The new token was deliberately **not** revoked, the journal is kept. | Fix the disk, then check the key names: `awk -F= '{print NR": "$1}' ~/vt/secrets.env`. If the store is readable, the next run verifies whatever it holds. If not, restore `secrets.env` from the repair backup (REPAIR-PLAN §6.3), then run by hand. |
| `verify: rc=N` with `verify\|` lines, then `restore: store holds Y again` | The new token did not prove itself. Store restored, new token revoked, old token untouched. | Read the `verify\|` FAIL lines using REPAIR-PLAN §2.3 and §5.1: `L.unreachable` points at the sentinel URL or proxy, heartbeat `_error` at the killswitch URL, `governor status` at the governor, `D.expired` or `D.revoked` at the token. A `rc=97` line means `verify-vt: verify_vt_field.py sha256 ... is not the pinned ...`: someone changed the verifier. |
| `verify: TIMED OUT after 120 s` | The estate or vt code hung. Same handling as above. | Tomorrow retries. |
| `verify\| [earlier output truncated]` | The verifier printed more than 64 KiB; only the complete lines of the last 64 KiB are shown. A following `[its last 64 KiB hold no complete line; not shown]` means one line filled the whole window. | Run the verifier by hand to see all of it. |
| `verify\|` lines with `<redacted>` or an id shown as `1a2b3c4d...` | The verifier printed the secret (whole, or 8 or more of its characters) or a full token id; the tool masked it. | If the secret shows up there, the verifier is printing it: fix the verifier. |
| `restore: FAILED (...)` + `NOT revoked: the store holds it` + `result: ... store STILL HOLDS X (the new token)` | Verification failed and the write back failed too. vt holds the new, unverified but active token; the old token is still active. Journal kept. | Fix the disk. The next run verifies the new token again; it is kept on a pass and undone on a fail. |
| `restore: NOT done: old token Y is EXPIRED ...` (or `not found`, or `REVOKED` after `--renew-revoked`) | Verification failed, but putting Y back would leave vt with no working token. vt keeps the new, active token. Journal kept. | Read the `verify\|` lines. The next run verifies again. |
| `restore: the store no longer holds X; not touching it` + `result: ... (neither the old nor the new token)` | Someone wrote another token into `secrets.env` during verification. The tool left it there. | Find out who. The next run revokes X if the store still does not hold it. |
| `store: VT_FIELD_TOKEN_ID no longer holds X after verification ... Old token NOT revoked` | `secrets.env` was changed while the verifier ran (for example a `cp -p secrets.env.bak`). The pass does not cover what vt will use, so the old token was kept. | Find out who. The next run revokes X if the store still does not hold it. |
| `tokens: cannot decide safely without both tokens' state` | A token read failed after verification. Nothing restored or revoked. | Nothing: the next run reads them again. |
| `restore: ... byte-for-byte identical to before the renewal: False` | Other bytes of the store changed during the renewal (after a crash, most likely). The token value was restored. | Check the key names: `awk -F= '{print NR": "$1}' ~/vt/secrets.env`. |
| `revoke-new: ... revoke FAILED` or `NOT confirmed revoked` + `journal: kept` | An orphan token may still be active. | Nothing: the next run revokes it first, then sweeps that mint's window again. |
| `revoke-old: Y revoke FAILED ...` or `NOT confirmed revoked ...; Journal kept (phase verified)`, rc 1 | Renewed and proven, but the old token is still active until it expires. | Nothing: the next run retries only the revoke. |
| `recovery: X is not in the agent's token list either: the id the mint answer named was never issued; sweeping ...` | A journal named a token the authority never issued (a rewritten mint answer whose confirmation also failed). Its revoke can never succeed, so the run swept for the token that mint created, ledgered `mint_answer_never_issued`, cleared the journal and went on. | Treat as a security incident, as for `HTTP 201 without a new token id`. |
| `recovery: X revoked` + `recovery: sweeping for another token that mint created (its run may not have finished a sweep)` + `sweep:` lines | A journal named a token that never reached the store; X is now revoked. The run that wrote the journal may have abandoned an untrusted mint answer whose sweep could not list the tokens, so the mint's window was swept again with the journal's own snapshot and start time: `sweep: no orphan token found` (the usual case after a crash), or `sweep: orphan Y revoked` (ledgered with `orphans_revoked`), then `journal: cleared`. With `sweep: could not list tokens` + `recovery: journal kept`, the next run sweeps again. | An orphan here means an earlier mint answer did not name the token minted, or someone minted the same grant during that mint (§1 "It does not"): treat it as a security incident, as for `abandon: ...`. |
| `recovery: X is not a token of volatility-trader; sweeping for the token that mint created before refusing` + `sweep:` lines + `refused: token X does not belong to volatility-trader; refusing to revoke it` | A journal names another agent's token (a mint answer that named it). Every run sweeps that mint's window, then refuses, rc 2. | §4.2, as for the `agent_id` refusal above. |
| `NOT confirmed revoked: not found on 3 reads` repeating every day | The token is in the agent's token list but every read of it answers 404 (a persistent store race), or the list cannot be read (`is not taken as never issued`). | Check the token with the `delegation/tokens` command in 3.8. If it truly does not exist, reconcile the journal by hand (§4.2). |
| `ledger: token.renewed append FAILED ...; exit status unchanged` | The renewal stands, but the ledger lacks the tool's event. | The authority's `delegation.mint` and `delegation.revoke` events still record it. |
| `recovery: ...` lines at the top | The previous run was interrupted. This run reconciled it first. | Read what it did. Nothing else needed unless the run ends `refused:`. |
| A Python traceback | A bug. The journal stays, and the next run reconciles. | Keep the log and report it. |

**A known estate issue this tool works around.** Several services share one
SQLite connection across request threads and do not lock their reads. This
was reproduced for delegation-authority on 2026-09-12: 8 threads reading
tokens concurrently got 1,828 spurious "not found" results in 32,000 reads,
plus corrupted rows. agent-registry, kill-switch, spend-governor and
federation-broker have the same pattern in code.

The tool therefore reads a token 3 times before it believes a 404, treats a
read that answers another token's row as unreadable (never as that row's
state), and never counts a token as revoked unless the authority answers
`revoked: true` for exactly that token id. A verification that trips on the
race fails without harm: either the store is restored and the new token
revoked, or, if the tokens cannot be read afterwards, nothing is touched and
the next run retries.

The race itself is a platform bug and is not fixed here. Under concurrent
traffic it can also produce spurious sentinel verdicts for real agents.

**4.1 A check worth scheduling.** Nothing alerts on a failure. This prints
the last result and how many days vt's token has left:

```sh
tail -1 ~/vt/logs/token-renewal.log; python3 -B ~/vt-renewal/renew_token.py --agent volatility-trader --base http://127.0.0.1:18080 --env-file ~/vt/secrets.env --env-key VT_FIELD_TOKEN_ID --check | tail -1
curl -s 'http://127.0.0.1:18080/ledger/events?agent_id=volatility-trader&event_type=token.renewal_failed' | jq -c '.[-3:][] | {ts, payload}'
```

**4.2 An interrupted renewal.** If `~/vt/.renew-token/` holds a `.json`
file, a run died mid-renewal or refused. It holds token ids and the grant,
never a secret:

```sh
jq '{phase, started_at, old: .old_token[0:8], old_revoked, new: ((.new_token // "")[0:8])}' ~/vt/.renew-token/renew-volatility-trader-*.json
```

**While a journal in phase `minted` or `verified` is pending, a second live
token with vt's full grant may exist.** The next run reconciles it before
anything else; run the hand command in §4 to do it now.
- `phase: minting` means the mint's answer was lost. The run sweeps for the
  orphan.
- `phase: minted` means one of two things. If the new token is not in the
  store, it is revoked and then that mint's window is swept again (or, if it
  was never issued, the tokens are swept); if it belongs to another agent,
  every run sweeps that window and then refuses (`refused: token X does not
  belong to volatility-trader; refusing to revoke it`) until a human
  reconciles the journal (step 2 below). If the new token is in the store,
  both tokens are read, verification runs again, and the old token is revoked
  only if verification passes.
- `phase: verified` means verification passed; only the old token's revoke
  and the ledger remain. The run retries those, never verifies again and
  never rolls back.

**Never revoke vt's tokens by hand while a journal is pending.** A revoked old
token in phase `minted` reads as a revocation during the renewal, so the next
run revokes the new token as well (vt halts). A revoked new token makes every
run refuse until the journal is reconciled.

To reconcile by hand (only after a `refused:` line, or on Don's decision):
1. List vt's tokens with the `delegation/tokens` command in 3.8, and read the
   store's token with `grep -c '^VT_FIELD_TOKEN_ID=' ~/vt/secrets.env` and the
   §3.6 `--check` line (prefix only).
2. Decide which token vt should hold. Revoke, with the curl in REPAIR-PLAN
   §6.4, every active token with vt's grant that the store does not hold and
   that is named in the journal. Also revoke every active token with vt's
   exact grant (the same `granted_by` and scope list) that the store does not
   hold and that no journal names, unless Don knows what holds it: a mint
   answer rewritten to name another token (another agent's, for one) leaves
   the token that mint created in no journal, and the tool's sweeps find it
   only while the token list answers and its grant is the one asked for.
   Never revoke another agent's token that a journal names;
   report it to Don. An active vt token with any other grant that the store
   does not hold is part of the same incident: Don decides.
3. Only then delete the journal file.

---

## 5. Install for the ssl agents on rog-command (Windows)

Written 2026-09-13 and run against the harness (§6); **not installed**. Steps
marked **Don** create scheduled tasks on rog-command (persistent
configuration) or run a real renewal. Never open, `Get-Content` or `type`
anything in `C:\Users\donal\.field-local\` except the log files named below.

### 5.1 What differs from vt

- **The store.** `ssl-invoicing-agent` and `ssl-timekeeping-agent` share one
  token file, `C:\Users\donal\.field-local\tokens-gb10.json`, which
  `provision_ssl_agents.py` writes as `{"<agent_id>": "<token id>", ...}`.
  The tool swaps one top-level member's string value (`--json-file` /
  `--json-key`) and keeps every other byte, including the other agent's
  member. Both tokens expire 2026-10-08 (STATE.md); todo.md A3 wants them
  renewed before 2026-10-01, one day apart.
- **The verifier is the skills' own client.** `tools\ssl-verify-token.ps1`
  runs as `--verify-cmd` under `powershell.exe -File`. It dot-sources the shim
  beside it, `tools\field-rest.ps1`, which is the file both ssl `SKILL.md`
  files dot-source. It prints one `PASS` or `FAIL` line per check, runs all
  four, and exits 0 only if all pass:
  1. `token file`: the shim's own `Get-FieldToken` returns exactly the new id;
  2. `heartbeat`: the shim prints `killed=false`;
  3. `in scope`: the in-scope action is `ALLOW` with no clause (a shadowed
     `ALLOW shadow:...` fails);
  4. `out of scope`: the probe action `token renewal verification:
     out-of-scope probe` is `BLOCK D.scope`.

  It exits 1 before any check, and before any call, when `-TokensFile` (the
  same path as `--json-file`) is not an existing file (then it does not even
  load the shim), when the shim resolved its token file to any other path
  (compared exactly, case included), or when the client posture is not
  `enforce`; and 2 when `-Agent` or `-NewToken` is malformed (the shim's JSON
  lookup ignores case, so `SSL-INVOICING-AGENT` would read the real agent's
  token). The shim itself no longer replaces a `FIELD_TOKENS_FILE` that does
  not exist with the real token file (it did until 2026-09-13; a mutant
  verifier in a test once sent the real ssl token to a local harness that
  way), but the verifier does not rely on that. The tool
  counts every non-zero exit as a failed verification. Verdicts are read from
  the lines the shim prints, never from its return values. Each verification
  adds 2 conformance events to the agent's ledger: a `conformance.allow` for
  the in-scope action and a `conformance.block` `D.scope` for the probe.
- **The in-scope action** must be in the manifest's `delegation.scope` and not
  an escalation trigger: `read timesheet xlsx` for timekeeping, `read
  timesheets` for invoicing (a test checks both against the manifests).
- **`-File`, never `-Command`.** Measured on rog-command (Windows PowerShell
  5.1): `-File` returned the script's own exit code (0, 1, 2, 7 and 255 came
  back unchanged). `-Command "& script ..."` turned exits 2 and 7 into 1, and
  `-Command "& script ...; 'next'"` returned **0 for a failed verifier**, which
  the tool would take as proof. §6 has the test.
- **What is pinned, and what is not.** `renew_token.py` runs from a pinned copy
  in `C:\Users\donal\.field-local\renewal\`, so an edit to the working tree on
  Google Drive never reaches a scheduled run. The verifier and the shim run
  from the repo on Drive **on purpose**: the shim there is what the skills load
  on every run, and the verifier must prove that file, including any later
  change to it. A shim change that breaks the verifier's parsing fails
  verification, and the old token is kept; it cannot make one pass. If Drive
  is not available at run time, `powershell.exe -File` exits non-zero
  (4294770688 was measured for a missing script file) and the renewal is undone
  the same way.
- **Today's estate is unarmed.** STATE.md (2026-09-13) says nothing is armed,
  so the command below sends no `x-field-auth`. §5.6 adds the secret when A2
  arms.

### 5.2 Preconditions

In PowerShell on rog-command, as the user the skills run as:

```powershell
$repo = 'C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform'
$py = 'C:\Users\donal\AppData\Local\Python\pythoncore-3.14-64\python.exe'
& $py -I -c "import sys; print(sys.version)"
Test-Path "$repo\tools\ssl-verify-token.ps1", "$repo\tools\field-rest.ps1", 'C:\Users\donal\.field-local\tokens-gb10.json'
(Get-FileHash "$repo\tools\ssl-verify-token.ps1", "$repo\tools\field-rest.ps1" -Algorithm SHA256).Hash.ToLower()
[Environment]::GetEnvironmentVariable('FIELD_TOKENS_FILE', 'User'); [Environment]::GetEnvironmentVariable('FIELD_CLIENT_POSTURE', 'User')
"HOME=[$HOME]"
```

Expect:
- `3.14.2 ...` (the interpreter the tests ran; `-I` means only the standard
  library is used);
- `True` three times;
- `f51e659ed618255c19e8196feb4b873295d831674f42319a1a13743d9782b0cb` for ssl-verify-token.ps1;
- `f71dae75e5d9c609d87f88a5dd1b962ae6a4255f198e9ec364cf315bab331613` for field-rest.ps1;
- two empty lines (no user-level `FIELD_TOKENS_FILE` or
  `FIELD_CLIENT_POSTURE`: a Task Scheduler run inherits the user environment);
- `HOME=[C:\Users\donal]`, exactly, case included: the shim then resolves its
  token file to `C:\Users\donal\.field-local\tokens-gb10.json`, the verifier's
  `-TokensFile` in §5.4. Any other spelling makes every verification fail
  (`FAIL  the shim reads its token file from ...`), and the renewal is undone.

STOP if a hash differs: the verifier or the shim changed after this runbook
was tested. Run `tools\tests\test_ssl_renewal.py` (§6) before going on.

### 5.3 The install directory and the pinned tool

```powershell
New-Item -ItemType Directory -Force 'C:\Users\donal\.field-local\renewal\logs' | Out-Null
Copy-Item "$repo\tools\renew_token.py" 'C:\Users\donal\.field-local\renewal\renew_token.py'
(Get-FileHash 'C:\Users\donal\.field-local\renewal\renew_token.py' -Algorithm SHA256).Hash.ToLower()
```

Expect `3a0683588a5a90bd7b7bb6fac9ab2798907af5772c8be058f4d1b5c436d3df29`, the sha256 of the renew_token.py this runbook was tested with. STOP if it differs.

The log directory must exist: `cmd.exe` cannot redirect into a missing
directory, and then exits 1 with nothing logged.

### 5.4 The command

Task Scheduler runs `C:\Windows\System32\cmd.exe` with the arguments below,
because only a shell can append the tool's output to a log. `cmd /d /s /c`
strips the outer quotes and runs the rest as written; `\"` is a literal quote
for Python's argument parser, which is how the verify command keeps its own
quoted paths. `{agent}`, `{action}`, `{within}` and `{secret}` are filled in
per task; `{new_token}` is left for the tool. A test takes this exact
`$template` line out of this file and runs it through `cmd.exe` (§6).

```powershell
$template = '/d /s /c ""C:\Users\donal\AppData\Local\Python\pythoncore-3.14-64\python.exe" -I "C:\Users\donal\.field-local\renewal\renew_token.py" --agent {agent} --base http://10.0.0.62:18080 --json-file "C:\Users\donal\.field-local\tokens-gb10.json" --json-key {agent}{secret} --renew-within-days {within} --ttl-days 30 --verify-cmd "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform\tools\ssl-verify-token.ps1\" -Agent {agent} -TokensFile \"C:\Users\donal\.field-local\tokens-gb10.json\" -NewToken {new_token} -InScopeAction \"{action}\"" >> "C:\Users\donal\.field-local\renewal\logs\token-renewal-{agent}.log" 2>&1"'
$secret = ''
$tasks = @(
    @{ Agent = 'ssl-timekeeping-agent'; Action = 'read timesheet xlsx'; Within = '10'; At = '14:50' },
    @{ Agent = 'ssl-invoicing-agent'; Action = 'read timesheets'; Within = '9'; At = '15:05' }
)
```

Why these values:
- `--renew-within-days` 10 and 9: with both tokens expiring 2026-10-08, the
  first due runs are about 2026-09-28 (timekeeping) and 2026-09-29
  (invoicing): one day apart and before 2026-10-01 whatever the tokens' hour
  of expiry. Each renewal mints 30 days, so the stagger holds afterwards.
- 14:50 and 15:05: in Don's working day, so a failure is seen the same day,
  and 15 minutes apart. The two tasks share the store's lock (§5.7), so an
  overlap is a visible skip, never two renewals at once.
- `--ttl-days 30` matches the provisioned tokens.

### 5.5 Dry runs

GETs only; the second one also creates the empty store lock file and writes
one log line per step.

```powershell
foreach ($t in $tasks) {
    & $py -I 'C:\Users\donal\.field-local\renewal\renew_token.py' --agent $t.Agent --base http://10.0.0.62:18080 --json-file 'C:\Users\donal\.field-local\tokens-gb10.json' --json-key $t.Agent --renew-within-days $t.Within --check
    "rc=$LASTEXITCODE"
}
```

Expect, for each agent, `token: <prefix> agent=<agent> granted_by='Don Hagell,
Spin State Labs' scope=5 entries expires 2026-10-08...`, then `check: not
due: N days left` and `rc=0`.
STOP on `refused:`, on `rc=1`, and on `check: due` (the next command would
then renew for real).

Then run each task's exact command once, as Task Scheduler will:

```powershell
foreach ($t in $tasks) {
    $arguments = $template.Replace('{agent}', $t.Agent).Replace('{action}', $t.Action).Replace('{within}', $t.Within).Replace('{secret}', $secret)
    $p = Start-Process -FilePath 'C:\Windows\System32\cmd.exe' -ArgumentList $arguments -WorkingDirectory 'C:\Users\donal\.field-local\renewal' -Wait -PassThru -NoNewWindow
    "$($t.Agent) rc=$($p.ExitCode)"; Get-Content "C:\Users\donal\.field-local\renewal\logs\token-renewal-$($t.Agent).log" -Tail 3
}
```

Expect `rc=0` and each log ending `journal: none`, `token: ...` and `not
due: N days left (...)`.

### 5.6 Register the tasks (Don)

```powershell
foreach ($t in $tasks) {
    $arguments = $template.Replace('{agent}', $t.Agent).Replace('{action}', $t.Action).Replace('{within}', $t.Within).Replace('{secret}', $secret)
    $taskAction = New-ScheduledTaskAction -Execute 'C:\Windows\System32\cmd.exe' -Argument $arguments -WorkingDirectory 'C:\Users\donal\.field-local\renewal'
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.At
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskPath '\FIELD\' -TaskName "token-renewal-$($t.Agent)" -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'FIELD token renewal: docs/runbooks/token-renewal.md section 5'
}
Get-ScheduledTask -TaskPath '\FIELD\' | ForEach-Object { '{0} logon={1} daily-at={2} StartWhenAvailable={3}' -f $_.TaskName, $_.Principal.LogonType, $_.Triggers[0].StartBoundary, $_.Settings.StartWhenAvailable }
```

Expect two lines, each `logon=Interactive` and `StartWhenAvailable=True`.

What the settings mean:
- **Interactive logon only, never a stored password.** The task runs only
  while Don is logged on, in his session, with his environment. No password is
  given to Task Scheduler, so none is stored. The cost: a console window
  flashes for the few seconds a run takes.
- **StartWhenAvailable.** A run missed because the laptop was off or logged
  off starts at the next logon. The 7-to-10-day window leaves many retries.
- **Daily**, at the time in `$tasks`; at most one instance, stopped after 30
  minutes (a renewal takes seconds; about 2 s against the harness, verifier
  included), and it runs on battery.
- **Last Run Result** is the tool's exit status: `0x0` renewed or not due,
  `0x1` failed (or the log directory is missing), `0x2` refused, `0x3` lock
  held. The log says which step.

Before registering, the same objects were built with `New-ScheduledTask` on
rog-command without registering them, and read back as `Interactive`,
`StartWhenAvailable=True`, daily; `Register-ScheduledTask` itself was NOT run.

**When A2 (the perimeter secret) arms**, before the estate starts refusing
requests without the header: set

```powershell
$secret = ' --secret-file "C:\Users\donal\.field-local\gb10-estate-secret"'
```

and re-run the registration loop with `Register-ScheduledTask ... -Force`.
That path is the shim's default secret file (`field-rest.ps1`
`Get-FieldSecretFilePath`), so the tool and the skills read the same secret.
It is UNVERIFIED on disk: this runbook was written without looking inside
`.field-local`. If the file does not exist the tool refuses (`refused:
--secret-file is not readable`, rc 2); without the flag an armed estate
answers `token: GET <prefix> failed (HTTP 401) (x-field-auth missing or
wrong); nothing written`, rc 1.

### 5.7 The lock, and the skills that do not take it

**The lock file.** Every run takes `C:\Users\donal\.field-local\.tokens-gb10.json.renew-lock`
(an msvcrt byte lock, created empty on the first run and left in place), so
the two tasks, which share one store, never renew at the same time. The
second logs `skipped: lock held (...)` and exits 3; tomorrow retries. No
`--lock-file` is passed, because no other process takes a lock that matters.
The journal, when one exists, is in `C:\Users\donal\.field-local\.renew-token\`.

**The ssl skills do not take the renewal lock.** This was checked by reading
`tools\field-rest.ps1`, not assumed:
- The shim resolves the token file's path once, when it is dot-sourced
  (`$script:FieldTokens`): `FIELD_TOKENS_FILE` when it is set, and then only
  that path (a missing file means no token and a BLOCK); otherwise
  `$HOME\.field-local\tokens-gb10.json`, and, when that file does not exist,
  `C:\Users\donal\.field-local\tokens-gb10.json`.
- It reads the file again on **every** `Invoke-FieldCheck` (`Get-FieldToken`:
  `Get-Content -Raw | ConvertFrom-Json`, then the agent's member), and sends
  that id in the same call's `POST /sentinel/check`, with `-TimeoutSec 15`.
- `Get-FieldHeartbeat`, `Send-FieldCheckin` and `Send-FieldSpend` send no
  token.
- Nothing keeps a token between calls. Both `SKILL.md` files call
  `Invoke-FieldCheck` before each governed action.

So a skill session running during a renewal sees this:
- before the swap, it presents the old token, which is active: normal verdicts;
- between the swap and the old token's revoke, it presents either token; both
  are active with the same grant: normal verdicts;
- after the revoke, it reads and presents the new token: normal verdicts.

**The race window** is one `Invoke-FieldCheck` that read the file **before**
the swap and whose request reaches the sentinel's token introspection
**after** the revoke. Between the swap and the revoke the tool runs the whole
verifier (a PowerShell start plus three estate calls, about 1.5 s against the
harness) and then reads both tokens again, so that one request must have been
in flight longer than all of that, and it is bounded by the shim's 15 s
timeout. Its outcome is fail-closed: the sentinel answers `BLOCK D.revoked`
(or the call times out, which the shim treats as `BLOCK`),
`Invoke-FieldCheck` returns `$false`, and the skill stops before that action.
The next hook call reads the new token. A revoked token can never be
allowed, because the sentinel introspects the token on every check. What the
race costs is one refused action and a re-run of the skill; it cannot let an
action through. When verification fails, the roles swap and the bound is the
same: a hook that read the new token before the restore and reaches the
sentinel after the new token's revoke is refused, and its next call reads the
old token again.

**The file itself.** The swap is an atomic rename, so a reader gets the whole
old file or the whole new one. If a reader has the file open at the instant of
the rename, Windows refuses the rename: measured on rog-command, a reader
opened with `FileShare.ReadWrite`, and also with `ReadWrite, Delete`, made
`os.replace` fail with `PermissionError` (WinError 5). The tool then changes
nothing and revokes the new token (`swap: write failed (PermissionError);
the original bytes are still in place`, rc 1; tomorrow retries). If it happens
on a restore, the new token is kept unrevoked with its journal (§4, `restore:
FAILED`). That exact collision with a skill's `Get-Content` was not produced
in a test; both tool paths are tested with an injected write failure.

**Do not run `provision_ssl_agents.py`** while a renewal can run. It rewrites
the same file without a lock. The tool refuses to swap a store that changed
after it was read, and keeps the old token if the store changes during
verification, but a rewrite in the milliseconds between its last read and the
old token's revoke is not caught.

### 5.8 Reading an ssl failure

`Get-Content C:\Users\donal\.field-local\renewal\logs\token-renewal-<agent>.log -Tail 40`.
The table in §4 applies; the tool lines are the same. The verifier adds these:

| `verify\|` line | Meaning | What to do |
|---|---|---|
| `FAIL  the shim reads its token file from '<path>', not -TokensFile '<path>': no call made` | The shim resolved another file than the one the renewal swapped (a `FIELD_TOKENS_FILE` in the user environment, or another `$HOME` spelling). No request was sent. The tool restored the file and revoked the new token. | Make the shim's path and `--json-file` the same file (§5.2). |
| `FAIL  -TokensFile '<path>' is not an existing file: shim not loaded, no call made` | `$template` names a token file that does not exist. | Fix `$template`, then re-register. |
| `FAIL  token file <path> holds <X> for <agent> (want <Y>)` | The shim reads the right file, but its member for the agent is not the new id (or is missing). The skills would keep presenting X. The tool restored the file and revoked Y. | Find what rewrote the member; see §5.7. |
| `FAIL  heartbeat: FIELD heartbeat <agent> killed=true status=<s> -> HALT` | The agent is killed or retired. | Nothing: a renewal never outranks a kill. Tomorrow's mint answers 409 until the agent is revived. |
| `FAIL  heartbeat: FIELD heartbeat <agent> UNREACHABLE (...)` | The kill-switch route or the estate is down. Every skill run would halt too. | Check the estate. Tomorrow retries. |
| `FAIL  in scope: ... -> BLOCK D.scope` | `$tasks` names an action the manifest does not grant. | Fix `Action` in `$tasks`, then re-register. |
| `FAIL  in scope: ... -> ESCALATE E.escalation_trigger` | `$tasks` names an escalation trigger. | Use a non-trigger action. |
| `FAIL  in scope: ... -> BLOCK D.revoked` / `D.expired` / `D.token` | The shim presented a token that is not live. | Read the `tokens:` line; the tool's own checks decide what happens (§4). |
| `FAIL  in scope: ... -> BLOCK L.unreachable` / `ESCALATE E.spend_cap` | Ledger unreachable / the governor has no cap for the agent. | Fix the estate; tomorrow retries. |
| `FAIL  out of scope: ... -> ALLOW shadow:D.scope` | The sentinel is running in `log_only` (it defaults to that when `FIELD_SENTINEL_MODE` is not `enforce`). | Fix the estate's sentinel mode. The skills are not being enforced either. |
| `FAIL  client posture is 'log_only', not enforce ...` | `FIELD_CLIENT_POSTURE` is set in the user environment. | Remove it, unless the estate is deliberately log_only. |
| `FAIL  -Agent is not a registry agent id ...` / `FAIL  -NewToken is not a lowercase uuid ...`, `verify: rc=2` | `$template` or `$tasks` was edited wrongly. | Re-register from this section. |
| `FAIL  shim not found: <path>`, or `verify: rc=4294770688` with no `PASS`/`FAIL` line | Google Drive was not available at run time. | Nothing if once; tomorrow retries. |
| `FAIL  unexpected error (<type>): ...` | A bug, or a shim that no longer defines the hooks. | Keep the log and report it. |

### 5.9 Uninstall

```powershell
Unregister-ScheduledTask -TaskPath '\FIELD\' -TaskName 'token-renewal-ssl-timekeeping-agent' -Confirm:$false
Unregister-ScheduledTask -TaskPath '\FIELD\' -TaskName 'token-renewal-ssl-invoicing-agent' -Confirm:$false
Get-ChildItem 'C:\Users\donal\.field-local\.renew-token' -ErrorAction SilentlyContinue | Select-Object Name
```

If a journal is listed, a renewal was interrupted: reconcile it (§4.2) before
deleting `C:\Users\donal\.field-local\renewal`, `.renew-token` and
`.tokens-gb10.json.renew-lock`.

---

## 6. Evidence (rog-command)

### 6.1 Version 1.5: a sweep left unfinished behind a journal that names the token (2026-09-13)

Nothing below ran on the GB10, against a live estate, or in Task Scheduler,
and nothing read `C:\Users\donal\.field-local`. The files measured:
- `tools/renew_token.py` version 1.5: `3a0683588a5a90bd7b7bb6fac9ab2798907af5772c8be058f4d1b5c436d3df29`
- the verifier and the shim are unchanged from 1.3 (the §5.2 pins).

**What changed from 1.4, and why.** A re-verification of 1.4 found that the
sweep 1.4 added for an untrusted mint answer ran only in the run that
abandoned the mint. If that sweep could not list the tokens and the revoke
of the named token failed too, the run kept the journal naming that token
(`journal: kept for the next run`). That journal does not record that a
sweep is still owed, so the next run revoked the named token, cleared the
journal and renewed (rc 0), and the token the mint really created stayed
active with no journal naming it. On the hop this runbook assumes can
misbehave, that takes one run: a replaced answer (or a rewritten id whose
confirmation shows another grant), then a 500 to the token list and a 500 to
the revoke. 1.3's confirmation path had the same gap. When the named token
belonged to another agent, the same unlisted sweep ended in the refusal
(rc 2), and every later run refused on that journal without sweeping.

1.5 changes recovery only. When a minted journal's token never reached the
store, the run revokes that token and then sweeps the agent's tokens again
before it clears the journal. The sweep uses the journal's own snapshot and
start time, so a late recovery sweeps that mint's window and not the day it
runs, and it leaves the named id out. A sweep that cannot list the tokens
keeps the journal, and an orphan it revokes is ledgered as
`orphans_revoked`. A journal token of another agent is swept for in the same
way before the run refuses. A revoke that is not confirmed keeps the journal
without a sweep, as before. This sweep also runs after an ordinary crash
between the mint and the swap, where it finds nothing unless someone minted
the same grant during that mint (§1 "It does not"). Guarantee 6, "It does
not", §2, §4 (three rows changed, two new) and §4.2 were corrected.

| What | Where | Result |
|---|---|---|
| The re-verifier's probes against 1.4 (`1b44bae6…`) in a scratch copy: Q1, a replaced answer, and Q1b, the confirmation path, each with the sweep's token list and the named revoke answering 500 | Windows 10, venv Python 3.14.2; harness with shared secret and DOA roster armed | 2 failed, as reported. Run 1: `sweep: could not list tokens`, `revoke-new: … revoke FAILED`, `journal: kept for the next run`, rc 1. Run 2: `recovery: … revoked`, `journal: cleared`, `result: renewed`, rc 0, with the real mint still active |
| A scratch probe against 1.4 of the same list failure when the answer names another agent's token (by id, and as its whole row), three runs each | same | 2 failed: rc 2 in all three runs, no sweep after run 1, the real mint active throughout |
| The 7 new renew tests against 1.4 (the final test module in a scratch copy of 1.4) | same | 7 failed. Both unfinished-sweep paths: the real mint left active after run 2. Both answers naming another agent's token, the two window cases and the kept journal: no sweep line where the test requires one |
| The same 7 against 1.5 in a scratch copy | same | 7 passed, 45 s |
| `tools/tests/test_renew_token.py`, in a run of all of `tools/tests` | same | 166 passed, 5 skipped (the POSIX-only tests). The 164 tests of 1.4 are unmodified; 4 test functions, 7 cases, are new. The whole run: 396 passed, 6 skipped, 1 failed, 19 min; the failure was the runbook pin test, on 1.4's full pin in §6.2, which this revision abbreviates |
| The re-verifiers' probes against 1.5 in a scratch copy: Q1, Q1b, Q2 and Q3 (`test_vr_probe.py`), P1 to P3 (`test_final_probe.py`), the 4 probes of 1.2's defects (`test_reverify_new.py`), and the two scratch probes above | same | 13 passed, 230 s. Q1 run 2: `recovery: sweeping for another token that mint created ...`, `sweep: orphan … revoked`, `journal: cleared`, then renewed. With another agent's token, run 2 sweeps the real mint and refuses; run 3 finds no orphan and refuses |
| Mutants of the fix: 8 single changes, each in its own scratch copy of 1.5, then the 63 renew tests that `-k` selects (recovery, crash, journal, sweep, orphan, never issued, 404, the lost, differing and untrusted answers, another agent) with `-x`, plus an unmutated baseline; then the 7 new tests without `-x` | same | 7 of 8 fail; the baseline passed (63 passed, 170 s). No sweep after the revoke: 5 of the 7 new tests (all but the other-agent cases). No sweep before the refusal: both other-agent cases. The journal cleared after a sweep that could not list: the kept-journal test. The window taken from the recovering run: the ten-minutes case. The snapshot dropped: the during-the-mint case, and one unfinished-sweep case depending on which other tokens fell in the window. `orphans_revoked` not ledgered: both unfinished-sweep cases. The sweep moved before the revoke: 5 of the 7. The survivor keeps the named id in the recovery sweep's snapshot: equivalent, since that id is revoked, or is another agent's, before the sweep reads the list |
| `tools/tests/test_ssl_renewal.py`, same run | same, plus Windows PowerShell 5.1 | In the whole run, 23 passed and the pin test failed as above. Run again on this runbook's final bytes: 24 passed. Unmodified except the version in one log assertion (1.4 to 1.5) |
| `tools/tests/test_field_rest_secret.py`, same run | same | 31 passed; unmodified (the shim did not change) |

**Not verified (1.5).**
- Everything listed for 1.4, 1.3 and 1.2 still applies, including the
  `journal_failed` double fault and the in-run sweeps' use of the old token.
  `verify_vt_field.py`, the GB10 wrapper, the WSL/POSIX runs and Linux CI
  were not re-run for 1.5.
- The mutants ran against the 63 tests that `-k` selects (with `-x`) and the
  7 new tests (without), not against the whole module.
- A journal naming another agent's token still needs a human (§4.2): 1.5
  adds only the sweep before each refusal.

### 6.2 Version 1.4: a mint answer replaced by another token's row (2026-09-13)

Nothing below ran on the GB10, against a live estate, or in Task Scheduler,
and nothing read `C:\Users\donal\.field-local`. The files measured:
- `tools/renew_token.py` version 1.4: `1b44bae6…`
- the verifier and the shim are unchanged from 1.3 (the §5.2 pins).

**What changed from 1.3, and why.** A final re-verification of 1.3 found a
sibling of 1.3's own fix. A mint answer that itself showed another grant,
lifetime or row went straight to `abandon: mint response differs ...`
without a sweep; 1.3 had added the sweep only where the confirmation `GET`
disagreed. So a hop that replaced the whole answer body with another token's
row, instead of only its id, got past both the snapshot rule and the sweep:
- the row of a token minted for the agent during the mint with another
  scope: 1.3 revoked that token and cleared the journal, the token the mint
  really created stayed active with no journal naming it, and the next run
  renewed (rc 0) with it still active;
- the row of another agent's token: 1.3 refused to revoke it (rc 2) before
  any sweep, so the real mint stayed active, and every later run refused on
  the journal naming the other agent's token; §4.2 revoked only tokens a
  journal names, so it missed the real mint too.

1.4 sweeps first on a differing answer, leaving out the id the answer names,
then revokes that id or refuses it (guarantee 6). A request altered in
transit whose answer names the real mint still revokes it by that id, after
`sweep: no orphan token found`, and clears the journal as 1.3 did. The
intent is kept when the sweep revoked a token or could not list the tokens.
The sweep is safe here for the reasons it is safe elsewhere: it touches only
a token absent from the pre-mint snapshot (which always counts the current
token), of this agent, with the exact grantor and scope list asked for, not
revoked, issued between 2 minutes before and 2.5 minutes after the intent,
and neither the old token nor, now, the id the answer names. The runbook's
guarantee 6, "It does not", the §4 row, §4.2 (a journal naming another
agent's token; step 2 now also covers unjournaled tokens with vt's exact
grant) and the §2 excerpts were corrected. The `UUID` line's spacing was
fixed.

| What | Where | Result |
|---|---|---|
| The re-verifier's probe module (`test_final_probe.py`: P1 a concurrent other-grant row, P2 another agent's id only, P3 another agent's row) against 1.3 (`82a45e53…`) in a scratch tree | Windows 10, venv Python 3.14.2; harness with shared secret and DOA roster armed | 2 failed, 1 passed, as reported: P1 rc 1 with the real mint active and no journal, and still active after the next run renewed; P3 rc 2 with the real mint active and unswept on both runs; P2 passes |
| The same module and the re-verifier's 4 probes of 1.2's defects (`test_reverify_new.py`) against 1.4 in a scratch copy | same | 7 passed. P1: `sweep: orphan … revoked`, `journal: intent kept`, and the next run `sweep: no orphan token found` then renews. P3: `sweep: orphan … revoked`, then `refused: token … does not belong to canary-gb10`, rc 2 |
| The 3 new renew tests against 1.3 (the final test module copied into the scratch tree) | same | 3 failed: the real mint left active (both replaced-answer tests), and no `sweep: could not list tokens` line (the list-failure test) |
| `tools/tests/test_renew_token.py` | same | 159 passed, 5 skipped (the POSIX-only tests), 283 s. The 156 tests of 1.3 are unmodified; the proxy gained 3 faults (`answer_row_of`, `answer_concurrent_row`, `list_fail_after_mint`) and 3 tests are new |
| Mutants of the fix: 7 single changes, each in its own scratch copy of 1.4, then the 41 renew tests that `-k` selects (mint, sweep, orphan, lifetime, re-attribution, confirmation, never issued, 404) with `-x`, plus an unmutated baseline; then, without `-x`, 9 tests of the differing-answer paths (the 3 new ones, both lifetime parameters, the widened scope, the other grantor, the other agent, and the interrupted mint whose sweep cannot list) | same | 7 of 7 fail; the baseline passed (41 passed, 193 s). No sweep for a differing answer: all 3 new tests. The one-line candidate (sweep, then always clear the journal): the concurrent-row and list-failure tests, on their journal assertions only; it does revoke the real mint in both replaced-answer tests. The intent kept only when the sweep could not list: the concurrent-row test. Only when it revoked a token: the list-failure test. The named id not left out of the sweep: both lifetime parameters (the journal was no longer cleared). The sweep after the revoke: the other-agent test. A differing answer handled like an untrusted confirmation: both lifetime parameters and the grantor test |
| `tools/tests/test_ssl_renewal.py` | same, plus Windows PowerShell 5.1 | 24 passed, 85 s. The 24 tests of 1.3 are unmodified except the version in one log assertion (1.3 to 1.4) |
| `tools/tests/test_field_rest_secret.py` | same | 31 passed, 70 s; unmodified (the shim did not change) |
| A scratch probe of the limit in §1 "It does not": the proxy widens the request's scope and puts a concurrent other-grant token's row in the answer | same | as documented: `sweep: no orphan token found`, the named token revoked, `journal: cleared`, rc 1, and the widened token the mint created still active |

**Not verified (1.4).**
- Everything listed for 1.3 and 1.2 still applies. `verify_vt_field.py`,
  the GB10 wrapper, the WSL/POSIX runs and Linux CI were not re-run for 1.4.
- The mutants ran against the 41 tests that `-k` selects (with `-x`) and
  the 9 differing-answer tests (without), not against the whole module.
- A disk failure writing the minted journal (`journal_failed`) still abandons
  without a sweep. If the answer had also been replaced by another token's
  row, the real mint would stay active and unjournaled. That double fault is
  neither handled nor tested.
- Every sweep inside a run leaves alone the old token it started from, not a
  fresh read of the store (as in 1.3): a same-grant token written into the
  store during the seconds of the mint would be swept. Read in the code, not
  tested.

### 6.3 Version 1.3, the verifier's `-TokensFile` and the shim's token file (2026-09-13)

Nothing below ran on the GB10, against a live estate, or in Task Scheduler,
and nothing read `C:\Users\donal\.field-local`. Every run that needed the
shim's old token-file fallback used a copy of the shim whose path literals
point into a temp directory (the tests' decoy shim). The files measured:
- `tools/renew_token.py` version 1.3: `82a45e53…`
- `tools/ssl-verify-token.ps1`: `f51e659ed618255c19e8196feb4b873295d831674f42319a1a13743d9782b0cb`
- `tools/field-rest.ps1` (changed, not committed): `f71dae75e5d9c609d87f88a5dd1b962ae6a4255f198e9ec364cf315bab331613`

**What changed from 1.2, and why.** A re-verification of 1.2 reproduced four
defects in the tool against the real services, and found two more by reading
the PowerShell side:
- A mint answer naming a token the agent already had. With the same grant,
  1.2 swapped that token in, verified it, revoked the current token and
  exited 0, and the token really minted stayed active with no journal. With
  another grant, 1.2 revoked that unrelated token and cleared the journal. A
  uuid never issued left a journal whose revoke could never be confirmed,
  and every later run stopped on it. 1.3 never revokes a token from its
  pre-mint snapshot except the current token after verification. Such
  answers, and an id that answers 404 and is missing from a fresh token list,
  are lost answers: sweep, and keep the intent journal. A confirmation that
  shows another grant, or a 404 for an id the list does carry, also sweeps.
  Recovery sweeps for a journaled id that was never issued, and a journal
  naming a snapshot token is refused (guarantee 6).
- The lifetime was not compared. A hop that rewrote `ttl_seconds` to 90 got
  a 90-second token swapped in and the 30-day token revoked, rc 0. 1.3
  requires `expires_at - issued_at` within 5 s of the TTL asked for, in the
  answer and in the fresh read (guarantee 2).
- No test pinned the relay's 8-character mask. A mutant masking the secret
  only from 12 characters passed the whole 1.2 module. 1.3's module prints
  isolated 7-, 8-, 9- and 11-character fragments of the secret and of a token
  id.
- `field-rest.ps1` replaced a `FIELD_TOKENS_FILE` that did not exist with the
  real token file, and the verifier never checked which file the shim read.
  The shim now uses a set `FIELD_TOKENS_FILE` and nothing else, and the
  verifier takes `-TokensFile` (§5.1, §5.4). `test_field_rest_secret.py` now
  runs the real shim only with an existing temp token file (it writes `{}`
  when a test did not), as `test_ssl_renewal.py` already did.
- The pins are for LF bytes, and `core.autocrlf=true` would have changed them
  on any checkout. `.gitattributes` now checks the three files out with LF.

| What | Where | Result |
|---|---|---|
| The re-verifier's 4 probe tests (`test_reverify_new.py`) against 1.2 (`15b9d1c1…`) in a scratch tree | Windows 10, venv Python 3.14.2; harness with shared secret and DOA roster armed | 4 of 4 fail their safety assertions, as reported: a pre-existing same-grant token swapped in and the current token revoked (rc 0, the real mint active and unjournaled); an unrelated other-grant token revoked; a never-issued uuid (the next run ends `recovery: journal kept`, rc 1); a 90-second token swapped in (rc 0) |
| `tools/tests/test_renew_token.py` | same | 156 passed, 5 skipped (the POSIX-only tests), 216 s. The 142 tests of 1.2 are unmodified except: 3 parameters added to the mint-answer test (whose setup now also mints two earlier tokens and asserts they stay untouched), 1 row added to the malformed-journal table, and 2 proxy faults added. 14 tests are new |
| The new renew tests against 1.2 in a scratch tree (the final test module copied in, `-k` on the new and neighbouring tests) | same | 12 failed, 19 passed: the 3 new mint-answer parameters, the current token missing from the list, the concurrent other-grant token, the token that answers 404, both lifetime parameters, the lifetime the answer hides, the never-issued journal, the unreadable-list journal, and the new invalid-journal row. The 19 that pass are guards 1.2 already had and the fragment test (1.2 masks from 8; the mutation row shows what that test adds) |
| Tool mutants: 19 guards of the fix, each changed alone in a scratch copy of 1.3, then the WHOLE renew module run with `-x`, 4 at a time, plus an unmutated baseline under the same load | same | 19 of 19 fail the module; the baseline passed (156 passed, 5 skipped, 749 s under load). They include the re-verifier's R1 (secret masked from 12 characters), the id mask at 12, the mask at 7, a lifetime tolerance of an hour, the snapshot rule reverted to 1.2's, the current token not forced into the snapshot, the never-issued paths in the mint and in recovery, the sweep and the intent journal of an untrusted confirmation, and the invalid-journal rule. The list is scratch `mutate.py` |
| `tools/tests/test_ssl_renewal.py` | same, plus Windows PowerShell 5.1 | 24 passed, 65 s. The 16 tests of 1.2 are unmodified except the version in one log assertion (1.2 to 1.3) and two docstrings; 8 are new: the path test (5 parameters, including a control that passes), the existence test, the template test and the line-ending test. The two cmd.exe task tests now run the template with -TokensFile |
| The new verifier tests, the template test and the line-ending test against the pristine verifier, shim, runbook and `.gitattributes` | same | all fail: the unfixed verifier has no `-TokensFile` (the 5 parameters of the path test, and the existence test), the runbook template had no `-TokensFile`, and `git check-attr eol` answered `unspecified` for all three files |
| Verifier mutants: the path check, the existence check, `-TokensFile` never honoured, `-ceq` made `-eq`; each alone, then the whole ssl module except the pin test | same | 4 of 4 fail. `-eq` first survived (21 passed); the case-spelling parameter was added, and it then failed |
| `tools/tests/test_field_rest_secret.py` | same | 31 passed, 62 s. The 28 tests are unmodified; run_shim gained the guard and the decoy option, and 3 tests are new |
| The new shim tests against the pristine shim (as a decoy copy) | same | both "never replaced" parameters fail: the pristine shim resolved `tokens-typo.json` to the decoy's real-file path. The unset-variable test passes on both, by design (unchanged behaviour) |
| Shim mutants: 1.2's fallback restored for a set `FIELD_TOKENS_FILE`, and the unset-variable fallback removed | same; TARGETED: only the decoy tests of both modules (`-k`), so no mutant shim ran where it could reach `.field-local` | 2 of 2 fail (3 and 2 tests) |
| A hand run: the pristine verifier and shim (decoy copy), `FIELD_TOKENS_FILE` naming a missing file, a capture server as `FIELD_PROXY_URL` | same | the decoy's "real" token reached both sentinel checks. The fixed shim alone: no sentinel call. The fixed verifier with `-TokensFile` over the pristine shim: `FAIL  the shim reads its token file from ...`, no call. Scratch `demo6/` |
| A checkout under `core.autocrlf=true` (a scratch repo, `git add` then `git checkout-index`, no commit) | Git for Windows | pristine `.gitattributes`: all three hashes change (CRLF). New `.gitattributes`: all three unchanged |
| The in-process relay tests (4, with the new fragment test) and the 5 `test_posix_*` tests on 1.3 | WSL Ubuntu, Python 3.14.4, the minimal pytest shim | 4/4 and 5/5 pass |

**Not verified (1.3).**
- Everything listed for 1.2 below still applies: Task Scheduler, the real
  token file and estate, the timekeeping row, a skill's `Get-Content`
  colliding with the swap, and the §5.7 race.
- `verify_vt_field.py` and the GB10 wrapper were not re-run for 1.3.
- A token someone else mints for the agent during the seconds of the mint,
  with the exact grant and lifetime, and that a rewritten answer names, is
  indistinguishable from the tool's own mint (§1, "It does not").
- The 5-second lifetime tolerance is pinned from above (a one-minute
  difference fails). A tolerance of 0 would also pass the tests, because the
  harness's authority is exact.
- The shim change is live for the skills as soon as Google Drive syncs it. It
  changes behaviour only when `FIELD_TOKENS_FILE` is set to a missing file.
  The skills themselves were not run.
- `-TokensFile` is optional in the verifier, so a hand run without it still
  works; the scheduled command's use of it is checked by the runbook template
  test and exercised by the two `cmd.exe` task tests.
- Linux CI was not run.


### 6.4 Version 1.2 and the ssl install (2026-09-13)

Nothing below ran on the GB10, against a live estate, or in Task Scheduler.
The files measured:
- `tools/renew_token.py` version 1.2: `15b9d1c1…`
- `tools/ssl-verify-token.ps1`: `cadb5c1c…`
- `tools/field-rest.ps1` (unchanged, committed): `739abde6…`

**What changed from 1.1, and why.**
- Review finding E6: 1.1 relayed the last 64 KiB of the verify command's
  output from a byte offset, before redaction and id shortening. A secret or a
  full token id that straddled that offset printed from the cut onward. 1.2
  relays from the first complete line inside the window, and masks every run
  of 8 or more characters of the secret (verbatim or escaped) or of a full
  token id past its prefix, with line breaks ignored (guarantee 9).
- The docstring's step 9 now says what the code does: an old token revoked
  before the renewal began (`--renew-revoked`) is never put back either.
- `tools/ssl-verify-token.ps1` and `tools/tests/test_ssl_renewal.py` are new;
  §5 is rewritten from "not written" to a tested install.

| What | Where | Result |
|---|---|---|
| `tools/tests/test_renew_token.py` | Windows 10, venv Python 3.14.2; the tool runs as a subprocess of the base interpreter with `-I` against the real services in `estate_harness.py`, shared secret and DOA roster armed | 142 passed, 5 skipped (the POSIX-only tests), 177 s. 136 are 1.1's tests, unmodified; 6 are new (the relay) |
| The new relay tests (the two in-process tests over every cut offset and every wrap point, the escaped-form test, and the 3 real renewals) against tool 1.1 (`442fafe5…`) in a scratch tree | same | 6 of 6 fail. 5 fail on their leak assertions (at the first cut, 1 character into the secret, 1.1 already printed 29 fragments of 8 characters); the escaped-form test fails only because 1.1 has no `scrub` to call |
| The same cuts, offset by offset, on 1.1 and on 1.2 (scratch `offsets_matrix.py`) | same | 1.1 printed a fragment of 8 or more characters at 29 of the 36 cut offsets through the secret and 28 of the 35 through a token id, and part of the cut line at all 71. 1.2: at none |
| Relay mutants: 9 guards of the fix, each removed alone in a scratch copy, then the 6 relay tests run (`-k`, not the whole module) | same | 9 of 9 fail. A tenth candidate (drop the byte before the window when it is a line break) turned out to be equivalent to the line search that follows it; that dead branch was removed from the tool rather than left untested. A later re-verification showed that a mutant masking the secret only from 12 characters passed both these 6 tests and the whole module; 1.3 added the test that fails it (§6.3) |
| `tools/tests/test_ssl_renewal.py` | same, plus Windows PowerShell 5.1: the real verifier under `powershell.exe -File` dot-sourcing the real shim, `ssl-invoicing-agent` provisioned from its real manifest with the real lifecycle CLI; a second, unarmed estate for today's command; a real `log_only` sentinel process for one test | 16 passed, 63 s |
| Verifier mutants: 12 (each of the 4 checks forced to pass, the posture refusal, the `-Agent` and `-NewToken` guards, the missing-shim guard, the default shim path, and 3 exit codes), each in a scratch copy, then the WHOLE ssl module run except the pin test (which fails for any changed file by design) | same | 12 of 12 fail the module. One is killed on its message only: without the missing-shim guard the generic error path still exits 1 |
| The runbook's pin test, before the pins in this file were updated | same | failed on the stale 1.1 pin of `renew_token.py`, as it should |
| `tools/tests/test_field_rest_secret.py` (unchanged) | same | 28 passed, 63 s |
| The 5 `test_posix_*` tests, and the 3 in-process relay tests, on 1.2 | WSL Ubuntu, system Python 3.14.4, through the previous fixer's minimal pytest shim | 5/5 and 3/3 pass |
| Exit codes through `powershell.exe` | Windows PowerShell 5.1, a probe script | `-File`: 0, 1, 2, 7, 255 returned unchanged; a thrown error, a failing cmdlet under `$ErrorActionPreference = 'Stop'`, a missing mandatory parameter and a parse error all returned 1; a missing script returned 4294770688. `-Command "& script"`: 2 and 7 became 1. `cmd.exe /d /s /c "... >> log 2>&1"` returned 0, 1, 2 and 3 unchanged, and 1 when the log directory was missing |
| The task objects | the §5.6 registration loop, taken from this file, with `Register-ScheduledTask` replaced by `New-ScheduledTask` | both tasks: `cmd.exe`, `Interactive`, `Limited`, daily, `StartWhenAvailable=True`, `PT30M`, `IgnoreNew`, allowed on battery. Nothing registered (`\FIELD\` holds 0 tasks) |
| `os.replace` over a file a reader holds open | a PowerShell reader with `FileShare.ReadWrite`, then `ReadWrite, Delete` | both: `PermissionError` (WinError 5), the file unchanged |

**Not verified (1.2 and the ssl install).**
- `Register-ScheduledTask`, a real scheduled run, a missed run started by
  `StartWhenAvailable`, and the console window an Interactive task shows. The
  `cmd.exe` runs pass the arguments to `CreateProcess` exactly as §5.6 builds
  them, but they were not started by Task Scheduler.
- The ssl tokens, the real token file, the GB10 estate and its sentinel.
  Whether `C:\Users\donal\.field-local\gb10-estate-secret` exists was not
  looked at.
- Only `ssl-invoicing-agent`'s command was run. The timekeeping row was checked
  against its manifest (action granted, not a trigger), not run.
- A skill's own `Get-Content` colliding with the swap; only a held-open
  reader and the tool's injected write failures were tested.
- The race in §5.7 was reasoned from `field-rest.ps1` and timed against the
  harness (verifier about 1.5 s, whole renewal about 2 s); it was not
  reproduced with a concurrent skill session.
- The relay does not mask a fragment of 7 characters or fewer, or a value the
  verifier re-encoded; the in-process relay tests ran on WSL, the
  real-renewal relay tests on Windows only.
- `verify_vt_field.py` and the GB10 wrapper were not re-run for 1.2; the
  relay change is the only difference they would see.

### 6.5 Version 1.1 (2026-09-12)

Nothing below ran on the GB10 or against a live estate. The tool file measured is
`tools/renew_token.py` version 1.1 with sha256 `442fafe5…`.

**What changed from 1.0, and why.** An adversarial review of 1.0 (sha256
`df151563…`) reproduced, against the real services:
- recovery restoring a still-active old token after a human revoked vt's
  swapped-in token (guarantee 7 violated);
- a mint answer carrying the old id making the abandon path revoke vt's live
  token;
- a resumed renewal restoring an already revoked or expired old token over a
  working new one;
- an old token revoked while the store had been rolled back mid-verification,
  reported `renewed`, rc 0;
- a failed restore still revoking the token the store held, under a result
  line claiming the old token was back;
- a hand run without `--lock-file` treating a live cron run's journal as a
  crash;
- a verify command that tested nothing accepted as proof.

It also showed that the 1.0 claim "66 of 66 mutants killed" held only for
builder-chosen mutants run with `-k`: a full-module run of 60 independent guard
mutants left 33 survivors. Each defect above has a test that fails on 1.0.

| What | Where | Result |
|---|---|---|
| `tools/tests/test_renew_token.py` (sha256 `8ba9a10c…`) | Windows 10, venv Python 3.14.2. The tool runs as a subprocess of the base interpreter with `-I` (standard library only), against the real services in `estate_harness.py` with the shared secret AND a DOA roster armed | 136 passed, 5 skipped (the POSIX-only tests), 437 s, run alongside the estate_probe suite. Two earlier runs of the same tool gave 136 passed, 5 skipped |
| The same test module run against tool 1.0 (sha256 `df151563…`) | same | 30 failed, 106 passed, 5 skipped. The 30 are the tests for the defects above and for behaviour 1.0 did not have (phase `verified`, the store lock, `{new_token}`, the `old_revoked` journal field). The 106 that pass include the new tests that pin guards 1.0 already had |
| `tools/tests/test_estate_probe.py` (unchanged, run as a regression) | same | 27 passed, 253 s |
| Full-module mutation run: 109 guards, each removed alone in a scratch copy of 1.1, then the WHOLE module run (no `-k`, stopping at the first failure). The list, one guard per mutant, is `fmutate.py` in the fixer's scratch directory | same, 6 parallel scratch copies | 109 of 109 fail the module. The first pass (107 of 109) left two survivors, both hidden by a neighbouring rule: a base URL with no host (the cleartext rule refused it first, because the test ran with a secret) and an unknown journal phase (the missing-`new_token` rule refused it first). Their test cases were changed so only the rule under test can refuse, and both mutants, plus one mutant whose first version crashed the tool instead of removing its guard, were re-run against the final module: all 3 fail |
| The same mutants, where the first failing check was the log text and the exit code matched | same | 19 such mutants. Re-run with every text check removed from the killing test (and those neutralised tests confirmed to pass on 1.1): 17 still fail on token state, store bytes, journal or ledger. **2 fail on their message only**, because another rule refuses the same runs with the same exit code and nothing done: "a renewal needs `--verify-cmd`" (the `{new_token}` rule refuses a run without one) and "a `verified` journal needs a uuid `new_token`" (such a journal never matches the store and is refused) |
| The 5 `test_posix_*` tests (skipped on Windows) | WSL Ubuntu, system Python 3.14.4, through a minimal pytest shim (pytest is not installed there) | 5/5 pass. Each of 7 POSIX mutants fails at least one of them: owner guard, `fcntl.flock`, `chmod`, `killpg`, `start_new_session`, the lock released right after it is taken, and `--lock-file` replacing the store's lock |
| Python 3.12 compatibility | `ast.parse(..., feature_version=(3, 12))` of the tool (a syntax check, not a 3.12 run) | pass |

**Not verified.**
- Python 3.12 on aarch64 (the GB10) was not executed.
- `verify_vt_field.py` itself was not run against vt: it needs vt's code, which
  lives only on the GB10. The wrapper was tested in 1.0's pass with a stand-in
  that has the same interface; that POSIX smoke run (28/28) was not repeated
  for 1.1.
- The real Caddy proxy and a live estate were not used.
- The Windows ssl verifier in §5 was not written then (see §6.4).
- Disk faults (a failing or damaged store or journal write) were injected by
  wrapping the tool's `write_atomic` in a separate process, not produced by a
  real full disk. One restore failure was also produced on Windows with a real
  sharing violation (a reviewer scenario, re-run against 1.1).
- The mutation run covers the 109 guards the reviewer and the fixer listed, one
  mutant each. It is not every line: a guard nobody listed has no mutant.
- The POSIX lock test that proves both locks are held through the renewal
  (`test_posix_bash_flock_is_excluded_for_the_whole_renewal`) runs the locked
  section with a stand-in, not a real renewal; the real-renewal version of that
  proof ran on Windows only (msvcrt locks).
- Guarantee 7 (a revocation is never undone) is tested for revocations made
  while the verifier runs and while a crashed run's journal waits. A
  revocation landing in the milliseconds between the tool's re-read of the
  tokens and its own revoke of the old token is not tested.

**Deviations from the build brief, with reasons.**
- A revoked token is refused unless `--renew-revoked` is given. The brief
  counted a revoked token as due; renewing it automatically would undo a
  human's revocation.
- `--verify-cmd` is required for a renewal, and must contain `{new_token}`,
  because the brief's core guarantee is "proven before the old token is
  revoked".
- `--verify-timeout` was added, defaulting to the brief's 120 s.
- The intent journal, its `verified` phase and the token snapshot before the
  mint were added, so a lost mint response can be swept safely and a crash
  after the old token's revoke is finished rather than rolled back.
- The store's own lock is always taken in addition to `--lock-file`, so no
  combination of flags lets two renewals of one store run at once.
- The 3-read 404 rule and the exact-token-id revoke confirmation were added
  after the store race above was reproduced.
