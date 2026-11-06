# Estate re-probe, toolchain config diff, G27 staged (estate-deployer, 2026-11-06)

## 1. Re-probe (HIGH: read this turn)
- GB10 (ede21674, Stage 1 LOG-ONLY): 8/8 log-only, registry b885ebdab2948f13 x11 rows, dropped_unauthenticated/refused 0/0 on all eight, canary halted=False, work_ticks 6573, ledger 3612 events head 7a12b7b0c110c0b9 consistent, estate_probe 25/25. No rollback.
- Fly (main-3804d0b, v19, 3/3 checks): 8/8 log-only, 11 rows, drops 0/0 on all eight, continuity 3/3 vs pin 664/1645215d0770cced (event_count now 683). No rollback.

## 2. B-deploy-scripts: edits to the local source (FORCE-FIELD/tasks, nothing vendored)
- ESTATE_SHA: the shared pg-run.py already defaults to the live build (killswitch /health); no pinned SHA remains in gb10-require-scripts, gb10-log-only-scripts or deploy-stage0-scripts.
- Operators file from config: new `gb10-require-scripts/operators.conf` (OPS_STAGED_NAME, OPS_SHA16, OPS_ROWS, OPS_IDS), read by pg-run.py and passed as STAGE0_PG_OPS_*; _lib.sh reads them (ten-row defaults kept if absent). `fly-require-scripts/operators.conf` (same file) read by f4lib.sh (TEN_IDS, OPS_ROWS); f4a-2 wording follows. f4lib also gets `</dev/null` on fly calls (fly ssh ate the go-sentence stdin).
- NOT merged into the shared source (ruling-specific, kept in my patched copy): F4_SOAK_FLOOR_H=1, E1 = GB10 Stage 1 clean instead of Stage 3, E3 entrypoint `-ge 4`, flylib STAGE4-AWARE secrets filter.
- Not yet dry-run: the shared edits only passed `bash -n`/`ast.parse` and a pg-run `--bundle-only`.

### diff _lib.sh
```
35,36c35,38
< TEN_IDS="don don-admin don-breakglass job-provision-gb10 job-renewal-gb10 job-renewal-rog svc-delegation svc-killswitch svc-lifecycle svc-registry"
< OPS_ROWS=10
---
> # the operators file under test comes from operators.conf (pg-run.py passes it as STAGE0_PG_OPS_*); the defaults are the ten-row file of 2026-10-27
> TEN_IDS="${STAGE0_PG_OPS_IDS:-don,don-admin,don-breakglass,job-provision-gb10,job-renewal-gb10,job-renewal-rog,svc-delegation,svc-killswitch,svc-lifecycle,svc-registry}"
> TEN_IDS="${TEN_IDS//,/ }"
> OPS_ROWS="${STAGE0_PG_OPS_ROWS:-10}"
53c55
<   STAGED="$BKROOT/operators-staging/operators-ten-row.json"
---
>   STAGED="$BKROOT/operators-staging/${STAGE0_PG_OPS_STAGED_NAME:-operators-ten-row.json}"
63c65
<   OPS_SHA16="${STAGE0_PG_OPS_SHA16:-ce5a9abcba8d2509}"   # the ten-row file; MUST equal the hex Don typed in the Stage 1 sentence
---
>   OPS_SHA16="${STAGE0_PG_OPS_SHA16:-ce5a9abcba8d2509}"   # the file in operators.conf (default: the ten-row file); MUST equal the hex Don typed in the Stage 1 sentence
```

### diff pg-run.py
```
51a52,71
> OPS_CONF = HERE / "operators.conf"   # KEY=VALUE lines: the operators file the toolchain checks (staged name, sha16, rows, ids)
> OPS_CONF_KEYS = {"OPS_STAGED_NAME", "OPS_SHA16", "OPS_ROWS", "OPS_IDS"}
> 
> 
> def ops_conf_env() -> list:
>     """--env items STAGE0_PG_<KEY>=<value> from operators.conf (none if the file is absent: _lib.sh keeps its ten-row defaults)."""
>     out = []
>     if not OPS_CONF.is_file():
>         return out
>     for line in OPS_CONF.read_text(encoding="ascii").splitlines():
>         line = line.strip()
>         if not line or line.startswith("#"):
>             continue
>         k, _, v = line.partition("=")
>         if k.strip() not in OPS_CONF_KEYS:
>             raise SystemExit(f"pg-run: operators.conf: unknown key {k.strip()!r}")
>         out.append(f"STAGE0_PG_{k.strip()}={v.strip()}")
>     return out
> 
> 
104c124,125
<     for e in a.env:
---
>     given = {e.split("=", 1)[0] for e in a.env}   # an explicit --env wins over operators.conf
>     for e in [c for c in ops_conf_env() if c.split("=", 1)[0] not in given] + a.env:
```

### diff f4lib.sh
```
42,43c42,47
< readonly TEN_IDS="don don-admin don-breakglass job-provision-gb10 job-renewal-gb10 job-renewal-rog svc-delegation svc-killswitch svc-lifecycle svc-registry"
< readonly OPS_ROWS=10
---
> # the operators file under test: operators.conf next to this file (OPS_ROWS, OPS_IDS comma-separated); the defaults are the ten-row file of 2026-10-27
> _F4_CONF="$(dirname "${BASH_SOURCE[0]}")/operators.conf"
> _f4conf() { [ -f "$_F4_CONF" ] && sed -n "s/^$1=//p" "$_F4_CONF" | tr -d '' | tail -n 1 || true; }
> _ids=$(_f4conf OPS_IDS); _rows=$(_f4conf OPS_ROWS)
> readonly TEN_IDS="$(printf '%s' "${_ids:-don,don-admin,don-breakglass,job-provision-gb10,job-renewal-gb10,job-renewal-rog,svc-delegation,svc-killswitch,svc-lifecycle,svc-registry}" | tr ',' ' ')"
> readonly OPS_ROWS="${_rows:-10}"
132c136
< flyc() { FC_RC=0; FC_OUT=$("$FLY_CMD" "$@" 2>"$F4_ERRF" | tr -d '\r') || FC_RC=$?; }
---
> flyc() { FC_RC=0; FC_OUT=$("$FLY_CMD" "$@" </dev/null 2>"$F4_ERRF" | tr -d '\r') || FC_RC=$?; }
140c144
< RX() { "$FLY_CMD" ssh console -a "$APP" -C "$1" 2>&1 | tr -d '\r' | grep -v 'The handle is invalid' || true; }
---
> RX() { "$FLY_CMD" ssh console -a "$APP" -C "$1" </dev/null 2>&1 | tr -d '\r' | grep -v 'The handle is invalid' || true; }
146c150
<   out=$("$FLY_CMD" ssh sftp put "$1" "$2" -a "$APP" 2>&1 | tr -d '\r' | grep -v 'The handle is invalid' || true)
---
>   out=$("$FLY_CMD" ssh sftp put "$1" "$2" -a "$APP" </dev/null 2>&1 | tr -d '\r' | grep -v 'The handle is invalid' || true)
233,234c237,238
<   [ "$REG_IDS" = "$TEN_IDS" ] || die "$1: the ids are not the ten expected ids"
<   ok "$1: $REGPATH 0600 in a 0700 directory, sha256 $REG_SHA16, $REG_ROWS rows, the ten ids (load_registry, ids only)"
---
>   [ "$REG_IDS" = "$TEN_IDS" ] || die "$1: the ids are not the expected operators.conf ids"
>   ok "$1: $REGPATH 0600 in a 0700 directory, sha256 $REG_SHA16, $REG_ROWS rows, the expected ids (load_registry, ids only)"
```

## 3. G27 staged, NOT done (Don's)
`FORCE-FIELD/tasks/fly-require-scripts/g27-don-positive-path.sh`: one command, one kill + revive of canary-fly with Don's key via phase_g_check; key and perimeter secret read from files only, never printed. Defaults: key `~/.field-local/keys/don-20261027.key` (rotated, fingerprint 41bddfc7), perimeter secret `~/.field-local/keys/fly-perimeter.secret` (absent: Don must create it from the Fly FIELD_SHARED_SECRET). I did not read the key or check it matches the don row.
Browser tab: not opened. No record names where Don keeps the perimeter secret or his key (Fly never reveals secret values; no password manager is named in the repo or runbooks).

## 4. Gating
Stage 2/3 stay closed: need PRs 826, 832 (stage controller) plus 817/818 (G21/G22) on main, then red-team no-blockers, before any go sentence.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
