# Agent Incident Retro

**Force-Field-Defence-Shield · product P1 · v0.1 (local branch, not released)**

Offline, read-only review of your existing web logs that flags **rogue-agent
incidents** — a goal-seeking automated client that escalated from ordinary
requests to injection or probing, the pattern seen against Library and
Archives Canada and the US Dept of Education in 2026 (Project Torpedo
incident A6). Every finding is tied to source log lines whose sha-256 digests
are sealed in a **signed, hash-chained evidence pack** a third party can
verify.

Force-Field governs agents you *own*. This is the victim-side half:
accountability for agents you *don't* own. It reuses the FIELD platform's
evidence spine (`field-core` hash chain + Ed25519 signing) and runs with **no
network and no estate**.

## What it does

```
logs ─▶ parse ─▶ sessionize ─▶ S.* clauses ─▶ verdict + attribution grade
                                      ├─▶ signed evidence pack (hash chain, Ed25519)
                                      └─▶ report.md (per-session timelines, draft notice)
```

- **Parses** NCSA combined/common logs (`--format clf`) or JSON lines with a
  field preset (`--format jsonl --preset generic|cloudflare`, or `--field`).
- **Sessionizes** by `(client IP, user-agent)` with an idle-gap split.
- **Flags** sessions with the `S.*` clause pack (see SPEC §3.4): injection and
  debug/probe severity; the A6 behaviours `S.pivot` (benign→tampered on the
  same parameter) and `S.escalate-on-block` (hostile step after a 4xx);
  `S.silent-200` (hostile request answered 2xx — possible undetected
  success); weak automation (`S.cadence`); and attribution-only markers.
- **Links campaigns**: the same payload fingerprint from ≥2 client IPs.
- **Grades attribution** G0–G2 (never an accusation; see below).
- **Seals** a signed pack and writes a human-review report with a DRAFT
  incident notice.

## Use

```bash
retro keygen --out air.key --pub air.pub          # once; keep air.key off-box
retro synth  --out synth.log                       # a synthetic demo log (no real traffic)
retro scan   synth.log --out ./out --key air.key   # writes out/report.md + out/evidence-pack.json
retro verify ./out/evidence-pack.json --pub air.pub --report ./out/report.md --sources synth.log
```

`scan` exits 2 when any session is ESCALATE (so a scheduled run can alert from
its exit status), 0 otherwise. Authorized traffic is allowlisted with
`--allow-ip` / `--allow-ua` and is **listed, never suppressed**.

## Attribution grades (never an accusation)

| Grade | Meaning |
|---|---|
| G0 | no automation indicator observed |
| G1 | behaviour consistent with an automated, goal-seeking client; operator unknown |
| G2 | a self-declared marker observed in the user-agent — **a claim, spoofable, not proof of operator** |
| G3 | cryptographically verified agent identity — **Declared only; not implemented in v0.1** |

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Inputs are never modified | **Enforced in code** | inputs are opened `rb` only; `write_outputs` refuses any output path that `resolve()`s to, or `samefile()`s (hard link), an input; `tests/test_readonly.py::test_inputs_are_not_modified`, `::test_write_outputs_refuses_a_hardlinked_input` |
| No network client in the code path | **Enforced in code** | the package imports no socket/httpx/urllib network client (`tests/test_readonly.py::test_no_network_client_imported`); a socket + `getaddrinfo` guard over a full scan+verify catches a dial-out (`::test_no_network_sockets`). This is structural + a tripwire, not an egress firewall |
| A tampered evidence pack cannot verify clean | **Enforced in code** | `verify` recomputes the field-core hash chain, head, every event signature and the pack signature; `tests/test_evidence.py` mutates each (`::test_event_mutation_breaks_chain`, `::test_head_truncation_detected`, `::test_single_event_signature_tamper_detected`, `::test_pack_signature_tamper_detected`) |
| A cited log line that was altered is caught | **Enforced in code** | `verify --sources` re-hashes *every* cited line against the supplied file; `::test_source_line_tamper_detected`, `::test_any_cited_line_tamper_detected` (each cited line independently) |
| Verification trusts only the key the verifier supplies | **Enforced in code** | library and CLI both key off the supplied public key, not the pack's embedded PEM; `::test_resign_with_other_key_fails_pinned_fingerprint`, `tests/test_cli.py::test_verify_uses_supplied_pub_not_embedded` |
| Findings cannot be edited without breaking the pack | **Enforced in code** | each finding's sha-256 is bound into its signed ledger event; `::test_finding_edit_breaks_binding`, `::test_last_finding_edit_breaks_binding` |
| Detection is deterministic | **Enforced in code** | pure functions over parsed requests; no clock/network/RNG in the detection path; `::test_determinism_same_input_same_pack_bar_timestamp`, and `tests/test_cli.py::test_scan_is_deterministic_across_processes` (two subprocesses, equal packs bar timestamp/signature) |
| Attacker text cannot inject Markdown/HTML into the signed report | **Enforced in code** | every log-derived string is scrubbed of control chars and HTML-escaped before rendering (`report.safe`/`report.code`); `tests/test_report.py` feeds newline/heading/`<img>`/backtick payloads and asserts no injected block survives |
| The CLI verbs behave as documented | **Enforced in code** | `tests/test_cli.py` covers `scan` exit codes (2 on ESCALATE), `verify` exit codes, `--pub` honoured, and the `--sources`/`--report` "not checked" qualifier |
| `S.pivot` / `S.escalate-on-block` catch the A6 escalation on the synthetic fixture | **Enforced in code** (fixture) | `tests/test_synth_expectations.py` pins verdicts/grades on an author-written fixture — a regression guard, not evidence of field recall; see LIMITS |
| Attribution is graded G0–G2, never asserted | **Enforced in code** | `grade_for` can only return G0–G2 (`tests/test_clauses.py::test_grade_never_returns_g3_on_any_clause_set`); report/notice wording is hedged and tested (`tests/test_report.py::test_notice_is_not_an_accusation`) |
| The clause set catches *every* rogue agent | **Declared only** | signatures and thresholds are uncalibrated defaults; see LIMITS. This is a review aid, not a WAF or an IDS |
| Attribution identifies the operator | **Declared only** | a marker is a client claim; behaviour cannot separate an AI agent from a scripted scanner |
| A signed finding is a *true* finding | **Declared only** | the pack proves a finding and its cited lines were not altered after signing; it does **not** re-derive the verdict from the sources, so it cannot prove the signer ran the detector honestly. A second party re-running `scan` on the same logs is the check |

## LIMITS

- **Not a detector of record.** The payload signatures are a readable
  WAF-lite; slow-and-low probing (spaced beyond the pivot window), novel
  encodings and payloads it has no pattern for will be missed. The product's
  value is the *sequence* clauses and the *evidence trail*, not signature
  coverage.
- **Thresholds are uncalibrated.** 300 s pivot window, 1800 s session gap, 20
  requests / CV 0.35 cadence are defaults with no labelled corpus behind them
  yet. Building that corpus is P1's second job. Tune per engagement.
- **Attribution is observation, not proof.** A user-agent marker is spoofable
  (the synthetic fixture includes a spoofed one on purpose). G3 does not
  exist in v0.1.
- **Only as complete as the logs.** Requests the log never recorded cannot be
  reviewed; a WAF that dropped a request before logging hides it.
- **IP ≠ actor.** Shared egress, proxies and archive/scanner intermediaries
  (`S.launder`) mean the client IP is often not the originator.
- **Sessionization is a heuristic.** `(IP, UA)` splits merge distinct clients
  behind one NAT and split one client that rotates UA; campaign linking is the
  partial answer to rotation.
- **False ESCALATE is possible.** A benign client whose query happens to match a
  payload pattern (a SQL-ish API filter param, a search string with shell/SQL
  metacharacters) and who also trips a behaviour clause can be flagged
  ESCALATE. Known FP classes: operators browsing their own `/admin` or
  `/debug` paths after a 404; data-API clients sending `$where=…='…'` filters.
  Every finding is a lead to verify, not a conclusion; allowlist known internal
  operators and scanners with `--allow-ip`/`--allow-ua`.
- **Allowlists are spoofable.** `--allow-ua` matches a substring of a
  client-supplied user-agent, so an attacker who knows your allowlist string
  can mark itself AUTHORIZED. Prefer `--allow-ip` for anything load-bearing;
  AUTHORIZED sessions are always listed with their clauses, never deleted.
- **Campaign linking is coarse.** Fingerprints normalise digits, so two
  unrelated payloads that differ only in a number link as one "campaign", with
  no time bound. It is a lead for a human, not proof of a coordinated actor.
- **`--no-raw` removes raw log *text* only.** Derived fields (client IP, path,
  query, user-agent) are still in the pack because the findings need them;
  `--no-raw` is not anonymisation. Hold the pack as that data's custodian.
- **Wrong `--format` fails quietly in the data, loudly on stderr.** A format
  mismatch parses ~0 lines and reports no findings; `scan` prints a WARNING to
  stderr when over half the lines did not parse. Check the Inputs table's
  parsed/unparsed counts.

See `SPEC.md` for the full specification and the decisions taken.
