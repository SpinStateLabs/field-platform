# Agent Incident Retro

**Force-Field-Defence-Shield · product P1 · v0.1.1 (second independent review, 2026-10-12; not released)**

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
its exit status). It exits 3 when no session is ESCALATE but at least one
was AUTHORIZED by an allowlist, so an allowlist can never make a scheduled run go
quiet (the report still lists those sessions); 1 on an error (a refused
`--allow-ip`, a bad config, an unreadable log); 0 when nothing was escalated and
nothing was allowlisted. Authorized traffic is allowlisted with
`--allow-ip` / `--allow-ua` and is **listed, never suppressed**.

`--allow-ip` refuses a network wider than /8 (IPv4) or /32 for IPv6, `0.0.0.0/0`
and `::/0` included (clear error, exit 1, nothing scanned): a catch-all would mark
every client AUTHORIZED. An IPv4-mapped IPv6 network (`::ffff:a.b.c.d/N`, N >= 96)
is read as the IPv4 network it is. Single addresses and narrower networks are
accepted.

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
| Inputs are never modified | **Enforced in code** | inputs are opened `rb` only; `write_outputs` refuses any output path that `resolve()`s to, or `samefile()`s (hard link), an input; `tests/test_readonly.py::test_inputs_are_not_modified` spies every `open`/`io.open`/`os.open` of the input and asserts read-only mode, and asserts inode/size/mtime/ctime unchanged after a scan (a byte comparison alone would pass a rewrite); `::test_write_outputs_refuses_a_hardlinked_input` |
| No network client in the code path | **Enforced in code** | importing the package in a fresh interpreter pulls in none of `socket`, `ssl`, `http.client`, `urllib.request`, `urllib3`, `requests`, `httpx`, `aiohttp` (`tests/test_readonly.py::test_no_network_client_imported`, run in a subprocess because pytest itself imports `socket`); a socket + `getaddrinfo` guard over a full scan+verify catches a dial-out (`::test_no_network_sockets`). This is structural + a tripwire, not an egress firewall |
| A tampered evidence pack cannot verify clean | **Enforced in code** | `verify` recomputes the field-core hash chain, head, every event signature and the pack signature; `tests/test_evidence.py` mutates each (`::test_event_mutation_breaks_chain`, `::test_head_truncation_detected`, `::test_single_event_signature_tamper_detected`, `::test_pack_signature_tamper_detected`) |
| A cited log line that was altered is caught | **Enforced in code** | `verify --sources` re-hashes *every* cited line against the supplied file; `::test_source_line_tamper_detected`, `::test_any_cited_line_tamper_detected` (each cited line independently) |
| Verification trusts only the key the verifier supplies | **Enforced in code** | library and CLI both key off the supplied public key, not the pack's embedded PEM; `::test_resign_with_other_key_fails_pinned_fingerprint`, `tests/test_cli.py::test_verify_uses_supplied_pub_not_embedded`, and `::test_embedded_pem_swap_with_real_fingerprint_kept_fails` (attacker re-signs everything with their key, swaps the embedded PEM but keeps the real fingerprint string: the fingerprint check passes, the signature checks must still fail) |
| Findings cannot be edited without breaking the pack | **Enforced in code** | each finding's sha-256 is bound into its signed ledger event; `::test_finding_edit_breaks_binding`, `::test_last_finding_edit_breaks_binding` |
| Findings, verdicts and grades are deterministic | **Enforced in code** | pure functions over parsed requests; no clock/network/RNG in the detection path. Two scans of the same logs give byte-identical `findings`, `campaigns`, `summary`, `inputs` and `config` (`tests/test_cli.py::test_scan_is_deterministic_across_processes`, two subprocesses with fresh hash seeds and fresh keys). The **evidence chain is not** deterministic across runs: `generated_at`, `report_sha256`, `chain.head`, `signature` and every event's `event_id`/`ts`/`hash`/`prev_hash`/`signature` derive from the run timestamp (and the key); the test names exactly that set as the only fields allowed to differ. With the same timestamp and key the whole pack is byte-identical (`tests/test_evidence.py::test_determinism_same_input_same_pack_bar_timestamp`) |
| Attacker text cannot inject Markdown/HTML into the signed report | **Enforced in code** | every log-derived string is scrubbed of control, bidi and zero-width chars, then rendered in a code span whose fence is one backtick longer than the longest run in the text (`report.code`), or HTML-escaped with every inline Markdown character backslash-escaped (`report.safe`); `tests/test_report.py` feeds newline/heading/`<img>`/`<svg>` payloads, backtick runs of 1–6 (`::test_code_fence_is_one_longer_than_the_longest_backtick_run`), the reviewer's double-backtick user-agent (`::test_double_backtick_run_in_user_agent_cannot_close_the_code_span`) and mid-string `![t](url)`/`[x](url)` in a probed path and in the client field (`::test_inline_image_and_link_in_probe_path_are_not_live`, `::test_inline_image_and_link_in_client_ip_notice_are_not_live`), and asserts nothing is live outside a code span |
| The CLI verbs behave as documented | **Enforced in code** | `tests/test_cli.py` covers `scan` exit codes (2 on ESCALATE), `verify` exit codes, `--pub` honoured, the `--sources`/`--report` "not checked" qualifier, and that `verify --sources` with a file whose name matches no input label reports `0 of N compared … (label mismatch)` and FAILs rather than "N lines match" (`::test_verify_reports_zero_compared_on_label_mismatch_and_fails`) |
| Unparseable lines are never fatal (SPEC §3.1) | **Enforced in code** | both parsers are wrapped by `parsers.never_fatal`: any `Exception` from one line (OverflowError on a year-9999 timestamp with an offset, RecursionError on 100 000 nested brackets, ValueError on a 5000-digit integer, OverflowError on `1e400`) counts that line as unparsed; `BaseException` still propagates. `tests/test_parsers.py::test_hostile_line_is_unparsed_not_fatal` (11 cases, each also run through `read_input`), `::test_never_fatal_does_not_swallow_base_exceptions` |
| Classification cost is bounded per request | **Enforced in code** | one cap (`signatures.bounded`, 8 KB) in front of every regex entry point (`classify`, `hostile_params`, `is_automation_ua`), and no pattern has an unbounded run between two required tokens (`tests/test_signatures.py::test_no_pattern_has_an_unbounded_run_between_required_tokens`); eleven 16 KB adversarial inputs each classify in < 0.2 s (`::test_adversarial_16kb_input_classifies_fast`), a 1 MB value costs no more than 8 KB (`::test_cap_applies_in_every_regex_entry_point`) |
| `keygen` never overwrites without `--force` | **Enforced in code** | both `--out` and `--pub` are checked before anything is generated; with `--force` the private key is chmod 0600 after the write (the create-mode in `os.open` does not apply to an existing 0644 file). `tests/test_cli.py::test_keygen_refuses_to_overwrite_an_existing_pub_without_force`, `::test_keygen_refuses_to_overwrite_an_existing_private_key_without_force`, `::test_keygen_force_leaves_private_key_0600_even_over_a_0644_file` |
| Outputs are written atomically, pack first | **Enforced in code** | each output is written whole to a `mkstemp` file in the output directory and renamed into place, the signed pack before the report it binds; a failed pack write leaves no orphaned `report.md` and a failed rename leaves no temp file. `tests/test_readonly.py::test_pack_write_failure_leaves_no_report`, `::test_failed_rename_leaves_no_partial_output`, `::test_pack_lands_before_report` |
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
- **JSONL duplicate keys: last wins.** `json.loads` keeps the last of two
  identical keys in one record, so `{"ip":"1.1.1.1","ip":"9.9.9.9"}` is
  attributed to `9.9.9.9`. The line's bytes are hashed as logged, so the
  evidence still cites the real record; the attribution is what the standard
  parser gives.
- **Memory is bounded by the input, not by the tool.** Each input file is read
  whole into memory (its sha-256 is over the whole file) and a line of any
  length is held whole; a 10 MB log line costs 10 MB. Only the regex matchers
  are capped: they look at the first 8 KB of a path, a query key/value and a
  user-agent (`signatures.MAX_MATCH_LEN`), so a payload placed past 8 KB is not
  classified. Split very large logs before scanning.
- **Client addresses are normalised for grouping only.** `::ffff:203.0.113.5`
  and `203.0.113.5` are one session and match the same `--allow-ip` CIDR;
  `2001:DB8::1` and `2001:db8:0:0:0:0:0:1` likewise. The normalised form is
  the one shown in the finding; the cited log line keeps the spelling as logged.
  A client field that is not an IP literal (an XFF list, a hostname) is kept
  verbatim and never matches a CIDR entry.
- **`verify --sources` matches files by basename.** Input labels are the log
  files' basenames (`a.log`, `a.log#2` for a repeat). A renamed copy compares
  nothing and FAILs with `0 of N compared … (label mismatch)`; pass the files
  under their original names.

See `SPEC.md` for the full specification and the decisions taken.

## Changelog

- **v0.1.1 — second independent review, 2026-10-12.** Closed: code-span fence
  escape via a backtick run (HIGH); cubic `ssti` regex and the 8 KB cap missing
  from `hostile_params` (HIGH); SPEC §3.1 "never fatal" violated by
  OverflowError/RecursionError/ValueError on hostile lines (MEDIUM); mid-string
  Markdown links/images surviving `safe()` (MEDIUM); `keygen --pub` overwriting
  without `--force` and `--force` leaving a 0644 private key (MEDIUM); report
  written before the pack, orphaned on a pack write failure (MEDIUM). Also:
  bidi/zero-width controls scrubbed; client IPs normalised for sessions and
  allowlists; `verify` no longer says "match" over zero comparisons; the
  Enforced-vs-Declared tests strengthened (open-mode spy + inode/mtime check,
  embedded-PEM swap with real fingerprint, `socket`/`ssl`/`http.client`
  forbidden, determinism row worded to what is actually deterministic).
  Tests 65 → 113.
- **v0.1 — 2026-10-11.** First build (P1), first review.
