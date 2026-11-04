# Scout round 2 (14 new proposals, read-only, NOT run) and builder report for S-A1 (PR 490). UNVERIFIED (cloud, no GX10).
Two Sonnet scouts (Don asked "scout for cards"), areas not covered by P-1..P-25. For the coordinator to number. Every item needs its evidence re-checked on main before work. Re-check status below: "R" = I re-ran the scout's probe on main cd3b7690; others are scout reading only.

## Builder report: S-A1 (taken, built)
PR 490 (draft): https://github.com/SpinStateLabs/field-platform/pull/490, branch fix/authn-non-ascii-header-500, head ddf8b63993296f4982a5d2f64c3e04fa02d73890 (one commit on main cd3b7690, noreply identity). Reviewer needed.
Bug: authn.py:56 hmac.compare_digest on str raises TypeError for a non-ASCII header (R). Fix: compare bytes. Failing test first (5 red), green; field-core suite 1549 passed 2 skipped; one mutant (str compare) 5 red. Not checked: force-gateway api.py:260, operator_auth.py, operator_health.py for the same pattern. The test client normalises header bytes, so latin-1 vs UTF-8 on the wire is not testable through it.
Also earlier today: PR 488 (P-6) and PR 489 (P-1) were marked ready for review by Don's account; both still need an independent reviewer.

## Scout A (field-core, tools; field-mcp does not exist in the repo)
- S-A1 DONE (PR 490) authn non-ASCII header.
- S-A2 bug+test-gap, field-core delegation.py:20-33,54-55: DelegationToken issued_at/expires_at are plain datetime; status() against an aware now raises TypeError on naive input (scout ran it). Use AwareDatetime or coerce; check the delegation-authority mint path first. HIGH.
- S-A3 bug, field-core ledger.py:98-102: make_event accepts NaN/Infinity in payload; hash is over a NaN token, served JSON has null, re-verify fails (R). Reject non-finite at seal (allow_nan=False). Service reachability LOW (not read).
- S-A4 hardening, manifest.py ~107-111: SpendCap.limit accepts inf (R); also DelegationToken.max_spend_usd (not run). allow_inf_nan=False; check the JSON schema file. HIGH accepted, MEDIUM impact.
- S-A5 bug+test-gap, tools/fly_identity_check.py:189,197-203: a non-dict /health body (null, [], 5) makes check_health raise; add tests incl. the 65536-byte cap. HIGH (reading).
- S-A6 hardening, tools/provision_ssl_agents.py:103,363-364,381-382: module-level int(FIELD_TOKEN_TTL_DAYS); a non-dict tokens file fails after tokens were minted and not saved. MEDIUM.
- Dropped: renew_token.py:1398,1406 unquoted token_id (ids come from authority responses; LOW).

## Scout B (services, defence-shield)
- S-B1 bug+test-gap, force-gateway telemetry.py:91-94: _CORRECTION `that (is|'s) incorrect` misses "That's incorrect."; no direct analyze() tests. Fix to `that(?:\s+is|'s)\s+incorrect`; marker tests. HIGH.
- S-B2 hardening, force-gateway api.py:796-806: FORCE_HYGIENE_WINDOW/BAND/BASELINE_WINDOWS, FORCE_GATEWAY_LATENCY_BUDGET_MS, FORCE_GATEWAY_BYPASS_COOLDOWN parsed bare; junk raises at startup; window 0 and band nan silently disable drift (drift.py:78,91). Guarded resolvers like resolve_telemetry_window. HIGH crash, MEDIUM silent-disable.
- S-B3 bug, claude-approver config.py:38-54, core.py:1005-1007: _float_env accepts inf; Event.wait(inf) raises OverflowError (scout ran it) and kills the poller; halt wait could block. Reject non-finite, clamp. HIGH inf.
- S-B4 test-gap + design question, claude-approver core.py:956-973,1000-1001: /halt returns 200 even when sessions.list or events.send failed; only the archive failure is tested (test_approver_api.py:178-186). Pin the shape; Don decides 200 vs 502 or a flag. LOW on whether 200 is a defect.
- S-B5 hardening+test-gap, compliance-crosswalk api.py:229,238,239,230-232,37-49: collect_evidence interpolates agent_id unquoted, indexes e["event_type"] on any response, never exercised (monkeypatched at test_pack_api.py:218). Quote, constrain agent_id, guard shapes. HIGH untested, MEDIUM exploitability.
- S-B6 bug+hardening, agent-registry models.py:26-33,47-60,65-80: owner/name/domain accept whitespace-only; domain unconstrained. Stripping non-blank validator; PATCH domain "" test. MEDIUM-HIGH. Check how kill-switch matches domains first (not read).
- S-B7 bug+test-gap, agent-registry cli.py:96-104,177-185: `registry add` traceback on bad slug; scan missing file escapes as FileNotFoundError; docs promise exit 2. HIGH structure, MEDIUM behaviour.
- S-B8 bug+test-gap, defence-shield/agent-incident-retro evidence.py:199,231 and cli.py ~51,~120: verify_pack raises AttributeError on a malformed pack (scout ran 3 shapes); CLI json.loads unguarded; scan misses FileNotFoundError. Auditor-facing verifier. HIGH verify_pack, MEDIUM CLI.
- Notes (not cards): spend-governor `set-cap --from-manifest` silently ignores conflicting flags and `--token-limit 0` (cli.py ~83-86); governor, federation, gateway and registry CLIs interpolate agent_id/contract_id unquoted: fold into the P-4 quoting sweep. record_scenes.py, capture_scene3.py, record_scene4.py have no test (do not know if intended).
- Not read by scouts: rest of spend-governor core/api, claude-approver core, plugin SKILL docs, integration/video, agents/*.
