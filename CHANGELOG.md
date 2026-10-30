# Changelog

## Unreleased

### Changed - review rounds on main after batch P (2026-10-29 and 2026-10-30)
These are the 109 commits on main after the last one the section below names (3bbc9d3), up to main at 5808a5c, by committer date 73 on 2026-10-29 and 36 on 2026-10-30. They are grouped by the batch that merged them, the way `comms/STATUS.md` on the `comms` branch records the batches; a batch number with a PR number is the batch PR, and "source PR" marks a batch where the status log names only the source pull requests. Each entry is the commit subject without its card and reviewer references, then the commit id on main (`git log`). Nothing here says where anything is deployed, and no entry goes beyond what its commit message states: each claim is for a reviewer to check against the code. `tools/changelog_gap.py` lists any commit of main after the newest one this file names (report only).

Source changes first: the commits that touch a non-test source file (by `git show --name-only`; a docstring-only change counts), grouped by area.
- spend-governor: bound amounts, make the window sum overflow-safe, count dropped audit appends (516ca761); a legacy cap row above the bound is served clamped, logged and counted (75a9643e); the other integer inputs are bounded like MAX_AMOUNT (ab503664); a legacy policy row above a bound is served without re-validation, never loosened (241a941f); the legacy-cap warning comes once per stored row and process (e20c39a9); the _WarnOnce docstring states the limit of its guarantee; a test that two agents with identical legacy policy rows each warn once (89e233dc).
- fix: tool defaults and the sketch manifest no longer carry the private address (014c5497).
- test: estate_probe pins the --expect-mode refusal and the state between revive and drill (694a90e0).
- compose: a GB10 override that makes the posture variables required, with a static test (045a47bd).
- attestation-reporter: a count is a count of records, a list of non-dicts is unavailable (a4f1dedc).
- force-gateway: remove the unreferenced component_block (03aa112c); an unrecognised posture flag refuses to start (e114640c).
- conformance-sentinel: an unrecognised FIELD_SENTINEL_MODE refuses to start (19f1daab); the refusal never echoes the value and sentinel serve exits 2 with one line; runbook corrected (1350c324).
- field-core: an unrecognised FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM logs one line per process, never the value (6cc95b90).
- sealed-ledger: verify --anchors fails on a missing, unreadable, unparseable or empty anchors file (150ec14b); load_anchors raises on an absent anchors file instead of returning an empty list (7920c27f).
- spend-governor, docs: the once-per-row warning memory is atomic and bounded; the README gives the absolute-path command (483ba65e).
- compliance-crosswalk: the evidence-pack signer is a name on one line, at most 200 characters (822f2015); a reading that lacks a cited identifier flags the framework stale (cd5a9a89); the signer refuses invisible format characters; the operator procedure for a respelled-identifier flag (817e86f0).
- operator_keygen: no key is left or shown for a registration that failed; a concurrent edit is refused (917a1d1a); --add-to runs its read-modify-write under a lock; any failure removes the key file; a failed key-file write is an error exit (5ba12004); an interrupt after the registry was replaced keeps the key file; key-file open failures are error: exits; lock descriptor close pinned (71d1d05e); one stderr line when the key file is kept after the registry replace; the full-length hash match pinned (483f2809).
- federation-broker: an inbound crossing needs a contract key (aa73df58); one active contract per counterparty org (409), a deterministic for_org, the keyless guard pinned before the scope check, demo asserts its verdicts (a9dc4f3d).
- agent-registry: a retired agent has no re-attestation; empty and name-only PATCH on a retired agent pinned; README wording (743d6d35).
- claude-approver: a send that failed after the API applied it is read as a duplicate, not a stranded rejection (a2629869); after an unknown-outcome send only a 400 or 409 reads as already applied; the duplicate record carries the earlier result (c6dc4490); a mixed-type processed_at orders by instant; the refresh interval, its 30 s skip and a failed read pinned (c5eeabe2); two ISO strings compare as instants; offsets, whitespace and lowercase z pinned (78073bcf); a value that is not a time is never later than a real time (c919daea); a value that is not a time is never stored as the cursor (ad424103).
- ops-console: the operator pair goes only on guarded writes; a harness test that reads, stream, export and check carry none (48acfa61); guarded writes refuse redirects; pins for hdrs() strictness, key globals and every guarded route (317c9e96).

Every commit, by batch (the entries above repeat here with the tests, docs and CI commits):
- Batch Q (PR 169): spend-governor: bound amounts, make the window sum overflow-safe, count dropped audit appends (516ca761).
- Batch R (PR 173): agent-incident-retro tests: a REVIEW-only scan exits 0, S.silent-200 boundaries (7e5257eb).
- Batch S (PR 174): ops-console tests: the dashboard escaping probe must prove something was rendered (3f5f40e9).
- Batch V (PR 177; the commits since batch S): fix: tool defaults and the sketch manifest no longer carry the private address (014c5497); test: the provision main test supplies the estate base URL (28dd2f12); docs: ssl skills name the FIELD_PROXY_URL requirement; old pin marked historical (4ca9019f); docs: STATE.md deploy-status remainder and other-file id classes (1fa5a2b6); docs: STATE.md restores the verbatim quote and uses neutral "step" wording (f7263fdb).
- Batch X (PR 179): delegation-authority: pin the exact-now expiry boundaries, the registry-502, the mint/revoke evidence fields and the request minimums (fc5ccd61); lifecycle-manager tests: PATCH answer code, unchanged step status, F-R12-2 test name (db3f5f81); test: operator_keygen mode pin holds under any umask; exact 0o600; empty --scopes with --check; alias and scope boundaries (313c52d7); delegation-authority tests: the grantor rule is ENFORCE-only, an alias mint needs a manifest_ref (e1bd49c3); test: estate_probe pins the --expect-mode refusal and the state between revive and drill (694a90e0); test: duplicate-key lint proven live on every scanned file (84ce303a); compose: a GB10 override that makes the posture variables required, with a static test (045a47bd).
- Batch Y (PR 180): compose: no-new-privileges, cap_drop ALL, read-only root on the platform services (06e7964a); ci: compose-smoke prints container state and logs when it fails (ff0f632d); compose: the proxy keeps NET_BIND_SERVICE so caddy's file capability can exec (b391f22a); compose, images: digest-pinned bases, pip constraints, a /health healthcheck per service (91bf0c79).
- Batch Z (PR 182): conformance-sentinel: pin upstream-error fail-closed, irreversible policies and the judge floor (1bae4fae).
- Batch AA (PR 183): field-agent tests: a chunked halt is closed before the chunk is parsed (6b2b02e2); test: crosswalk evidence pack pins the whole named-signer header and the Signature block (79145d02); attestation-reporter: a count is a count of records, a list of non-dicts is unavailable (a4f1dedc).
- Batch AB (PR 188): compose, ci, images: approver and GB10-only hardening, constrained approver install, container health in CI (56387d67).
- Batch AC (PR 190): tests, compose: GB10 required-posture overlay LOWs (cc2e9a47); force-gateway: remove the unreferenced component_block (03aa112c).
- Batch AD (PR 193): docs, tests: docs/ENVIRONMENT.md and an AST test that every variable read in src is listed (cdb80916).
- Batch AE (PR 194): tools: pin the duplicate-key lint's discovery, empty set, unhashable key and nested case (4511bc45).
- Batch AF (PR 197): tools/tests: test_phase_g_check settles for the service's own append bound, 1.5 s not 3 s (e0745507).
- Batch AG (PR 200): docs: README layout and development section, ROADMAP figure and arm64 wording (40108ec9); docs: README development section is true for every service; layout wording (84c2f217); docs: README, the defence-shield directory takes the same ../.. prefix (9ab9924d); ci, tests: the container-health step fails on a dead or absent container; pins catch re-escalation (30d8da6f); tests: executable fakes proven used, exited/paused/absent-then-healthy cases, compose merge modelled in the pins (0800d3ce).
- Batch AH (PR 205): docs, tests: ENVIRONMENT.md Component column compared with the scan; aliases and constant-held names followed (56e96174).
- Batch AI (PR 209): tools/tests: SETTLE_S is set per module by an autouse fixture, and the no-event wait is pinned (e8f0a82d).
- Batch AJ (PR 212): spend-governor: a legacy cap row above the bound is served clamped, logged and counted (75a9643e); tests: compose pins model !reset and the replaced keys, pin the host-level options, pin the call-log assertion (250bda88).
- Batch AK (PR 214): spend-governor: the other integer inputs are bounded like MAX_AMOUNT (ab503664); spend-governor: a legacy policy row above a bound is served without re-validation, never loosened (241a941f).
- Batch AL (PR 220): tools/tests: the fake clock of the _no_more tests is bounded, so a no-sleep mutant fails in seconds (c968e91e); spend-governor: the legacy-cap warning comes once per stored row and process (e20c39a9); docs: README names the three subprocess tests the relative-path recipe cannot run (68941e6f).
- Batch AM (PR 222): tools: a security lint over the CI workflows (f928347b).
- Batch AN (PR 225): conformance-sentinel: an unrecognised FIELD_SENTINEL_MODE refuses to start (19f1daab).
- Batch AO (source PR 223): force-gateway: an unrecognised posture flag refuses to start (e114640c); field-core: an unrecognised FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM logs one line per process, never the value (6cc95b90).
- Source PR 229: conformance-sentinel: the refusal never echoes the value and sentinel serve exits 2 with one line; runbook corrected (1350c324).
- Batch AP (source PR 224): sealed-ledger: verify --anchors fails on a missing, unreadable, unparseable or empty anchors file (150ec14b).
- Batch AQ (source PR 226): spend-governor, docs: the once-per-row warning memory is atomic and bounded; the README gives the absolute-path command (483ba65e).
- Batch AR (source PR 228): tools/tests: the workflow lint closes the missed spellings of the injection sink, pins the safe patterns, scans composite actions and the .yaml patterns (afee3b71).
- Batch AS (source PR 230): compliance-crosswalk: the evidence-pack signer is a name on one line, at most 200 characters (822f2015); compliance-crosswalk: a reading that lacks a cited identifier flags the framework stale (cd5a9a89).
- Batch AT: tests: normalise bind sources before the root check, long-syntax root bind pinned, ps-only call-log variant, service-level !reset (5454a8d7).
- Batch AU (source PRs 203, 204, 232): tools/tests: the duplicate-key lint is probed one level deeper on the real files, and the unhashable-key semantics are exact (b73a64da); operator_keygen: no key is left or shown for a registration that failed; a concurrent edit is refused (917a1d1a); compliance-crosswalk: pins for the pack, regwatch and lock-helper details the mutation round found unasserted (383064fc); spend-governor: the _WarnOnce docstring states the limit of its guarantee; a test that two agents with identical legacy policy rows each warn once (89e233dc).
- Batch AV (source PRs 239, 240, 242): tests, docs: the ENVIRONMENT.md scan follows copies, attribute aliases, bare getenv, in-tests and constants; First read and numeric defaults checked (37ee4a81); tools/tests: the workflow lint flags the whole github/inputs context as a value, the object filter and a dynamic key; unpinned spellings and write-all pinned (b267e266); compliance-crosswalk: the signer refuses invisible format characters; the operator procedure for a respelled-identifier flag (817e86f0).
- Batch AW (source PRs 246, 206): defence-shield: --allow-ip refuses a catch-all or too wide network, and scan exits 3 when an allowlist authorized a session (88219443); federation-broker: an inbound crossing needs a contract key (aa73df58); docs: five lines that still called a keyless contract acceptable inbound (3958e75e).
- Batch AX (source PR 243): tests: forbidden bind sources are trees, `${VAR:-/}` defaults expanded, the proxy-reset mutant differs only by the reset (82ec2106).
- Batch AY (source PR 244): sealed-ledger tests: a rotated ledger's claims about its archived prefix, and the surviving witness guards (4d4da945).
- Batch AZ (source PRs 247, 252): claude-approver: tests for the selection layers, the event-read rules, the usage guards and the heartbeat status (7aa82d61); tests: the regwatch byte cap at its boundary, a bounded lock clock, the dup-key probe below the second level, the warn-once docstring aside pinned (bcbdf2d3).
- Batch BA (source PRs 251, 254): agent-registry: a retired agent has no re-attestation; empty and name-only PATCH on a retired agent pinned; README wording (743d6d35); docs: ENVIRONMENT.md first-read line for agent-registry's FIELD_DATA_DIR moved one line (461ba7c9); operator_keygen: --add-to runs its read-modify-write under a lock; any failure removes the key file; a failed key-file write is an error exit (5ba12004).
- Batch BB (source PR 250): claude-approver: a send that failed after the API applied it is read as a duplicate, not a stranded rejection (a2629869); claude-approver: after an unknown-outcome send only a 400 or 409 reads as already applied; the duplicate record carries the earlier result (c6dc4490).
- Source PR 261: agent-registry: the guard-before-retired order pinned under ENFORCE; the CLI refusals pinned on stderr (ed22dda7).
- Batches BC to BF (source PRs 258, 259 and the commits between): agent-registry tests: the manifest-authorisation step of attest pinned against the retired check (525cac71); claude-approver: the events-read shortcut pinned one condition at a time; the mixed-type cursor fallback exercised (f74ea5f5); tests: the two size guards of a saved page pinned apart; the dup-key probe at the deepest mapping of the real files (bc001980).
- Batch BG (source PR 260): operator_keygen: an interrupt after the registry was replaced keeps the key file; key-file open failures are error: exits; lock descriptor close pinned (71d1d05e); operator_keygen: one stderr line when the key file is kept after the registry replace; the full-length hash match pinned (483f2809); tests: the existing key-file test expects the C-412 c contract, an `error:` exit, not a FileExistsError (4c995299).
- Batch BH (source PRs 264, 265): tests, compose: /run, /var/lib and the runtime state, credential directories below /home, every default and replacement spelling, a source out of the repository, driver_opts binds (d2bc319e); sealed-ledger tests: the rotation-event check of verify_bundle one comparison at a time on a relinked forgery; the witness events-array guard (9589c82f).
- Batches BI to BK (source PRs 270 to 272 and the commits between): claude-approver: a mixed-type processed_at orders by instant; the refresh interval, its 30 s skip and a failed read pinned (c5eeabe2); tests: the saved-page read bounded at cap + 1 (spy); the dup-key loader's own depth; the deepest-header helper pinned both ways (b7cc4319); sealed-ledger tests: a rotation event without segment_closed is refused (9daa02b6); tests: the key-file refusal text never carries a key (85c6cfdb).
- Batch BL (source PR 277): tests, compose: a home directory itself, the other credential places, ${HOME}, the repository root/.git/.env, more runtime state, base-file and merged volumes (f1f625f1).
- Batch BM (source PRs 279, 280): sealed-ledger tests: segment_closed of another type is refused (d8649d48); claude-approver: two ISO strings compare as instants; offsets, whitespace and lowercase z pinned (78073bcf).
- Batch BN (source PR 281): tests: the key-file refusal text carries no run of the key over 8 characters (3287f038).
- Batch BO (source PR 284): tests, compose: HOME and the other settled variables read before any default; more credential places, sockets and runtime state; a null volume override keeps the base (a7e00d33); tests, compose: restore the terraform.d credential entry (a mutant run left it out of the first push) (7e8f16ef).
- Batch BP (source PR 285): claude-approver: a value that is not a time is never later than a real time (c919daea); tests: the key-material helper's window boundaries are pinned (3ee2e5d2).
- Batch BQ (source PR 288): ops-console: the operator pair goes only on guarded writes; a harness test that reads, stream, export and check carry none (48acfa61).
- Batch BR (source PR 291): ci: pin pip and constrain every CI install; a test that keeps it so (61000ba7).
- Batch BS (source PRs 295, 293): tests: a lint for HTTP clients that read the proxy environment, with an allowlist of today's sites (9e6627f8); tests, compose: parents of credential trees, PWD, credential variables and more places forbidden (613ab50b).
- Batch BT (PRs 294, 296): docs: CHANGELOG for the review batches F to P, merged 2026-10-29 (e7e6304c); claude-approver: a value that is not a time is never stored as the cursor (ad424103).
- Batch BU (PR 307): ops-console: guarded writes refuse redirects; pins for hdrs() strictness, key globals and every guarded route (317c9e96); docs, tests: the token-renewal runbook's renew_token.py pin is the file's hash and a test keeps it so; the D-18 pre-check lists active rows only (d5c6e2d3); sealed-ledger: load_anchors raises on an absent anchors file instead of returning an empty list (7920c27f); federation-broker: one active contract per counterparty org (409), a deterministic for_org, the keyless guard pinned before the scope check, demo asserts its verdicts (a9dc4f3d).
- Batch BV (PR 312): tests, compose: the bind-source rule is an allowlist; the denylist stays as a second net (b929f126).
- Batch BW (PR 320): docs: estate total .35 (whole cents, floored as the governor shows them), current test count, dated snapshots labelled, FC-E-04..06 merged (e1f4bc74); ci: the build environment is pinned too: --build-constraint with hatchling, its dependencies and editables (7197205b); ci: no apostrophe in the new comment (a test shlex-parses the run block) (4e08651e); ops-console tests: a static audit that every HTML sink takes only escaped or constant text (5808a5cd).

### Changed - review rounds on main, batches F to P (PRs 126 to 159, merged 2026-10-29)
Each batch is one fast-forward of reviewed commits; the commit ids below are the ones on main (`git log`). The PR number is the batch PR; the source PR and card numbers are in each commit message and in `comms/STATUS.md` on the `comms` branch. Code behaviour is stated as the commits state it; nothing here says where anything is deployed.
- Batch F (PR 126): `renew_token` signs its ledger appends with the caller key when `FIELD_LEDGER_CALLER_ID` and `FIELD_LEDGER_CALLER_KEY` are set, counts a lost append as `dropped_ledger_appends=N` on the failure line, and a signing error sends no POST (80fdd1a, 18c4059); its signing tests run with the interpreter that has field-core's dependencies (29a924f) and the runbook says a system python loses the signed record (4c67c37). `todo.md` C2 follows the segments journal (8ae7dbf); the ops-console README states the shared secret has no secure-context gate (727a785).
- Batch G (PR 133): a retired agent's owner, domain and `manifest_ref` are frozen, refused 409 in every operator mode inside the same atomic store step as retired-is-terminal; the name stays editable (84570e7). ops-console tests: manifest symlink and size guard, the refusal ledger append, upstream and registry error text (ef0ba78), and the dashboard escaping pinned with a hostile-estate jsdom probe (d16c424). Docs: the Fly rehearsal log is removed from the tip and `STATE.md` drops deployed image, volume, snapshot and machine ids and present-tense deploy claims (6793a90, f75baab).
- Batch H (PR 142): `operator_keygen` tests for key file permissions and content, usage errors exiting 2 and the program entry (803dd35); claude-approver pins for the shadowed tool case, the split-batch rejected label, halt skips and deadline, and config shape checks (9cc9ed2); `STATE.md` present-tense estate lines and deploy-status headings removed (fb52eef).
- Batch I (PR 145): the estate's private address becomes `<gb10-lan-address>` in docs, comments and help text (c124b5c); independent tests use a documentation-range address (d42901c); the GB10 proxy's TLS address comes from `FIELD_GB10_LAN_IP`, required with no default, and CI uses an RFC 5737 documentation address (c771f7b); `estate_probe` gains `--expect-mode` on the status pairing, restores the canary after a catalogue run, bounds its reads (c90b3c2, c293b2a) and keeps its canary and token guards ahead of any write, with a static guard test (4847520); one `env` block in `compose-upgrade-smoke`, a duplicate key had made the workflow invalid (b07f648).
- Batch J (PR 149): tests that `register` fails closed on any answer but 201 or 409, reads after a 409 only on 200, and `on_behalf_of` has its own gate (0750b60); force-gateway pins for the upstream non-200 passthrough, the hygiene judge key and status guards, and the resolver (e9dcada).
- Batch K (PR 152): delegation-authority tests of the mint grantor rule end to end (907c142); a symlink loop in the ops-console manifest path is refused 404, not a 500 (26d95e6); a test that no workflow or compose file has a duplicate mapping key at any depth (c3b6a25).
- Batch L (PR 153): ops-console tests pin each containment check alone and the signed refusal append, built for the ledger client's own headers (97432d5, a97402f); dated notes on ADR packs 10, 07 and 02 (0acf2e6, 73bc4e7).
- Batch M (PR 154): field-agent pins for the canary halt body guards, `x3_check` refusals, the heartbeat-age boundary and federation argument checks (5d0515a); defence-shield pins for the allowlist negatives, the AUTHORIZED exit code and the detection boundaries (b099b28).
- Batch N (PR 155): `phase_g_check` closes two fail-opens: a keyed run needs at least two registry status changes, and without `--expect-mode` an inferred OFF is a FAIL and an inferred armed mode exits 4 (NOT VERIFIED), never 0; a failed check (1) outranks 4 (d2ce25f).
- Batch O (PR 156): the compliance-crosswalk evidence pack says it is a named-signer document, not a cryptographically signed one (README paragraph and Declared row, the pack header line, an ADR 07 wording note) (a946d26).
- Batch P (PR 159): `operator_keygen` validates the registry before writing or printing a key, so a refused `--add-to` leaves no key file or printed key whose hash was never registered (fd32d64); attestation-reporter: a wrong-shape ledger or token answer fails one metric closed (3bbc9d3).

### Changed - review rounds on main, 2026-10-28 (PRs 58 to 96)
Each line names the main commit; dates are the commit dates in `git log`. Merge evidence per PR is in `comms/STATUS.md` on the `comms` branch.
- Operators file and loader: format 2 break-glass id must be a `rotation:` sealed row (PR 58, 75a84c8); the break-glass alias belongs to the break-glass row alone (PR 63, 84d26a4) and is refused in the shared `validate_rows`, format 1 too (PR 64, a8bd47c); duplicate JSON keys are refused and deep nesting takes the designed refusal (ec60512, 2518d1d); one shared decoder `decode_registry_document` serves the loader, `operator_health` `slot_witness` and `operator_keygen --check`, so `--check` and the service agree on every file shape (PR 95, b1872ee).
- Observer: the sealed-ledger operator observer witnesses a content-only edit of the operators file (PR 61, ecb3ffd) and its bytes-only change event is documented (aaae5ec).
- Operator health: a refusal with no ledger to write to is counted as dropped (PR 66, a91b819).
- Alerts: ntfy push alerts with an alert-test CLI and runbook (b4d0495, 0a9fadb); an environment proxy never receives the alert, the module default opener is pinned against it (PR 59, 07f072a, e75d9bb); `stage_aborted` and `rotation_halted` classes (c6883e5).
- Clients and proxies: `field_agent.FieldClient` takes no environment proxy and reads a bounded reply (b5e07d0, 39d02e9).
- LLM callers: `field_core.llm.make_http_client` is the one way the hygiene judge, the sentinel judge and the crosswalk suggester build their Messages client, with `trust_env=False` so an environment proxy no longer receives the Anthropic key, the perimeter secret or the token id; a plain-http `FORCE_GATEWAY_URL` outside the estate is refused (`cleartext_ok`, `InsecureBaseURLError`) (PR 96, 7b54f26). Open follow-up F-C197-1 (PR 104); the claude-approver SDK client is not covered (F-C187-3, not deployed).
- Force-gateway: the upstream key never goes back to the caller and judge errors name the class only (45a36f5); warn once, opt-in `FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM`, wider base64 and prefix scrub, class-name error texts (PR 75, 9292246).
- Console edge: `X-Frame-Options`, `frame-ancestors` and `nosniff` on the ops-console catch-all of both Caddyfiles (0917267, e043257).
- Machine verifier (P35): the verifier identity reaches the canaries only, mint and revoke for the canaries alone; section 7 verification runs under `svc-verifier-<estate>` (PR 73, 583519d to 66aa869, 1845f49).
- Delegation: a list-bound identity cannot tell an unknown token from one it may not revoke (151cd3f); the unknown-token revoke 403 is a counted, ledgered refusal (PR 77, 444e49b).
- Registry: a retired agent cannot be reactivated by PATCH in any mode (D-22, 0843123); the retired-is-terminal rule sits in the store's atomic update (6f5ee96).
- Tests only: operator_health survivors (PR 79, ad33a60), spend-governor cap window (PR 81, 284f14b), kill-switch drill detection and `/liveness` cutoff (15a7304, b92ec10), sealed-ledger rename retry (70fa59f), observer fetch deadline (0b44dee), delegation red-team follows D-22 (7b4d6f7), field-core deep-nesting loader (2518d1d). Crosswalk README: FC-E-04..06 cite nothing (4cf73d5).

### Changed - Phase G Stage 1 and key rotation, 2026-10-27 (PRs 43 to 54)
- Key rotation R1 to R3: operators file format 2 parser (PR 53, b273d5b), lifecycle-manager builds operator auth headers per request (PR 51, 34d680c), and `verify-hash`, rotation state, roster digest and break-glass counters (PR 54, c8ecba7).
- Phase G: sign operator events in the form the ledger stores and count failed record appends (PR 52, cefb81b); per-process operator identities on the Fly machine (PR 44, f6c348f); `ops-console` refuses an operator key outside a secure context (PR 50, ca5e895).
- Hardening and follow-ups: observer whole-exchange deadline, `fullmatch`, ledger UNREADABLE vs busy, `field verify-chain` exit 2 (PR 45, d288a2f); `set_status` per-call headers, `estate_probe` RT1-RT3 pairing, P29 no-change re-provision (PR 46, efe430b); `ledger verify` with no ledger at `--path` exits 2 unless `--allow-empty` (PR 47, af17cc4); DOA job-grantor rows folded into `doa-roster.example.yaml`, `generate_doa_roster --job-rows` (PR 49, 3b3be05).
- P30: Claude 5.5 generation priced; session ids on sentinel and governor ledger rows (PR 43, ac2d981).

### Added - P28(c): `field_agent.field_client.FieldClient` (lifted from cost-optimizer)
- The cost-optimizer's stdlib FIELD client (`SpinStateLabs/cost-optimizer` 817aace, `field_client.py` +
  `safe_http.py`) now lives in `packages/field-agent` with its behaviour unchanged, re-exported as
  `field_agent.FieldClient` / `field_agent.FieldStop`, so the next FIELD-guarded gateway (deploy guide pattern D)
  does not re-implement the five fail-closed rules. Tests: the source's 13, 5 gap-closing additions and 6
  contract tests against the real sentinel, governor and kill-switch apps (in-process, no network). The
  cost-optimizer is not changed and still uses its own copy.

### Changed - Phase G Stage 0 follow-ups (code and descriptors)
- C-6 switched on in the compose and Fly descriptors: the ledger's operator observer runs (`FIELD_LEDGER_OBSERVE_EVERY` default 60 s,
  `FIELD_LEDGER_OBSERVE_HEALTH` = the seven other operator-block services), on the ledger only. CI's three smoke
  jobs check the start-up `operator.mode_changed` / `operator.registry_changed` rows on the real containers.
  The observer streams each `/health` body with a 64 KiB / 3 s cap (a trickled or huge answer is no answer).
  `phase_g_check` check 5 (collateral) lists observer rows (those two types, no agent id) as `[INFO]` instead
  of failing on them.
- `operator_on_behalf_of` is a reserved ledger key (field-core `RESERVED_KEYS`): a shared-secret caller can no
  longer put it on a row once an operator mode is armed; the registry records it only through field-core's
  `bind_on_behalf_of` (a `bypass_operator_list` identity), and the ledger keeps it only from a writer whose
  `ledger_attribute` `event_prefixes` reach the event type: any such holder on its own prefixes (design 2.2.1:
  `svc-registry` `registry.`, `svc-killswitch` `kill.`, `svc-delegation` `delegation.`, `svc-lifecycle`
  `lifecycle.`/`orphan.`), not only the registry.
- `sweep_kill` (C-11) is a known field-core scope in `EXPLICIT_ONLY`: `*` does not imply it for any `has_scope`
  reader, and `operator_keygen.py` writes it only when named.

### Added - pilot S2: `services/claude-approver` v0 (compose profile `approver`)
- A Claude Managed Agents client that answers every `always_ask` tool call (`evaluated_permission: ask`)
  with the conformance-sentinel's verdict: `allow` only on an exact `ALLOW` from a 200, every other
  outcome a `deny` (`<clause>: <reasons>`, `escalated: a human holds this item; ...`, or
  `claude-approver: <reason>`); kill-switch heartbeat per handled call; governor `/usage` from
  `session.usage` deltas with a restart-safe cursor; `POST /halt/{agent}` (interrupt, wait, archive) for the
  kill-switch allowlist; `/stats` with p50/p95 latency. Per-agent estate routing (`estate_base_url` +
  `secret_file`). Custom tools are not executed in v0. Own image (the only one with `anthropic>=2.3.0,<3`);
  never started by a plain `up`.

### Changed - Phase G Stage 0: field-core and `/health` (PR #32; code only)
- C-10: `assert_operator` is split into `bypass_operator_list` (skips a manifest's `authorized_operators` check)
  and `ledger_attribute` (reserved operator fields survive the ledger only on event types inside the row's
  `event_prefixes`). `*` implies neither. A registry file that still grants `assert_operator` is refused whole
  (503 under REQUIRE) and `operator_keygen.py` will not write it. This supersedes every `assert_operator`
  sentence in the entries below.
- C-18: every row needs `status` exactly `active` or `revoked` and lower-case hex; one bad row makes the file
  unavailable; zero active rows under REQUIRE is a 503. `operator_keygen.py --check FILE`; atomic `--add-to`.
- C-17: an unrecognised non-empty `FIELD_OPERATOR_REQUIRE` arms ENFORCE (fail closed) and logs one error.
- C-1: `FIELD_OPERATOR_KEY_FILE`, read on every call. C-15: `operator.unauthenticated` keeps `claimed_id` and is
  accepted from any shared-secret caller, `self_reported: true` unless the caller holds `ledger_attribute` (the
  ledger's own guard rows too); every other `operator.*` type is refused to every HTTP caller.
- C-8: `/health` on the eight flag-bearing services reports the operator mode, the registry file's sha256 prefix and
  row count, the service's own identity, the last registry error and drop/refusal counters (never a key, a key hash
  or a row). C-9: spend-governor and federation-broker guards ledger `operator.unauthenticated`. C-16:
  `operator.refused` under ENFORCE, at most 30 records per 60 s per service.
- Registry errors and records never echo a status value, an id or alias carrying the key prefix, or an unbounded
  request path (clipped to 200 characters, printable URL-path text only). The claimed `x-field-operator` value
  stored in ledger rows (`claimed_id`, `operator_claimed` on `operator.*`, `kill.*`, `ledger.legal_hold.*` and
  every other attributed row) is `(not shown)` when it could be a key: the key prefix, or a 40+ character
  unbroken token (an alias in a registry error: 24+); the ledger masks a `claimed_id` posted by any caller too.

### Added - Phase G: authenticated operators (code only)
- `field_core.operator_auth`: operator keys (`x-field-operator`, `x-field-operator-key`), a local
  `operators.json` verifier (sha256 only, constant-time, scoped), `FIELD_OPERATOR_REGISTRY`
  (log-only) and `FIELD_OPERATOR_REQUIRE` (enforce), both unset by default.
- Guarded writes: kill, kill/domain, revive, drill, attest, rotate, hold, hold/release, mint,
  decommission. 401 no key; 403 wrong key / mismatch / scope / not in `authorized_operators`
  (identical body); 503 when the operator registry is unreadable; 400 on malformed headers.
- Ledger payloads carry `operator_id_authenticated`, `operator_claimed`, `operator_key_fp`.
- `tools/operator_keygen.py`; internal callers present `FIELD_OPERATOR` / `FIELD_OPERATOR_KEY`.
- Kill-switch README Enforced-vs-Declared row; runbook section 7.

### Phase G review round (independent red team)
- Guarded: registry `PATCH` with `status`, delegation token revoke, ledger `/retention/apply`, lifecycle `/sweep`.
- `POST /events`: reserved operator keys are dropped unless the caller holds the `assert_operator` scope. (Superseded by C-10, PR #32: `ledger_attribute` with `event_prefixes`.)
- Unresolvable manifest denies; empty `authorized_operators` still requires authentication; body operator replaced by the authenticated id; BOM and lone-surrogate registry handling; bounded log-only ledger write; ops-console forwards the human's headers.

### Phase G second review round
- Registry PATCH honours `authorized_operators`; `registry_edit` scope for manifest_ref/owner; `retired -> active` refused.
- Guarded: `POST /agents` (`register`), ledger `/export` (confined to `FIELD_EXPORT_ROOT`), spend-governor caps/rate-limits/policies/escalations, federation contracts.
- Flags-OFF byte-identical (reserved-key rewrite and `operator.*` refusal only when armed); attribution-loss warning; capped log-only appends; ops-console sign-in panel.

### Phase G third review round
- `names` (display-name aliases) per operator so shipped manifests' `authorized_operators` match; `operator_keygen --alias`.
- The `assert_operator` exemption is shared by every `authorized_operators` check (kill-switch included). (Superseded by C-10, PR #32: `bypass_operator_list`.)
- Registry: no transition out of `retired`; `manifest_ref` edits must resolve; `domain` edits need `registry_edit`; combined PATCH needs the union of scopes.
- Nested reserved keys stripped; `operator.` event-type check ignores case and whitespace; agent-facing routes listed as declared-unguarded.

### Phase G fourth review round
- A registry with duplicate operator ids, an alias equal to an id, an alias shared by two operators, or the alias `*` fails closed (503); `operator_keygen` refuses to write such a row.
