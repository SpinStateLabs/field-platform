# C-537 (Lane 9, cloud-reviewer, read-only, no GX10): docs/agent-estate.md and docs/capstone-evidence/ on main b929f12: public safety and claims. Class and file:line only; no value printed.

VERDICT: agent-estate.md is public-safe (no address, hostname, email, path, key, flag value or deploy status found by scan or read) and its arithmetic is right except one rounding inconsistency already carded (C-474, PRs 311 and 313 pending). The capstone-evidence folder is clean of secrets; it carries one personal-path class (field-agent-run.log), one stale remote statement and estate-name wording (hardening.md), and an engine commit id in the scorecard files. Nothing needs urgent removal.

OBJECTIONS FIRST: (1) a regex scan finds shapes, not meaning; I also read agent-estate.md in full and the other files' estate wording by grep, not line by line (about 40 KB across 11 files; the scorecard JSON is 45 KB and was scanned, not read). (2) "Public safe" for an estate name such as GB10 is a policy question (C-561), not a defect I can settle. (3) Figures here are a 2026-08-11 snapshot of a synthetic demo fleet; I verified arithmetic and the price rates against code, not the telemetry itself (no stack here).

ASSUMPTIONS: main b929f12; price book in packages/field-core/src/field_core/pricing.py (`PRICE_BOOK_ID = "anthropic-list-2026-10-27"`, :49).

CLAIMS CHECKED (agent-estate.md)
TRUE
1. Token sums: input 80,000 + 120,000 + 60,000 = 260,000; output 12,000 + 30,000 + 15,000 = 57,000; total 317,000. HIGH (arithmetic).
2. Per-agent costs: crm-enrich 80,000 x $1/MTok + 12,000 x $5/MTok = $0.08 + $0.06 = $0.14; forecast 120,000 x $2 + 30,000 x $10 = $0.24 + $0.30 = $0.54; invoicing (Opus) 60,000 x $5 + 15,000 x $25 = $0.30 + $0.375 = $0.675. HIGH (arithmetic).
3. The Opus-versus-Haiku example: 75,000 tokens cost $0.675 on Opus and 60,000 x $1 + 15,000 x $5 = $0.06 + $0.075 = $0.135 on Haiku; ratio exactly 5x; Opus lists at 5x Haiku on both rates ($5 vs $1, $25 vs $5). HIGH.
4. Rates table equals code: claude-haiku-4-5 $1/$5, claude-sonnet-5 $2/$10, claude-opus-4-8 $5/$25: pricing.py:106, :110, :113 (`_p(in, out, cache)`); book id matches `PRICE_BOOK_ID`. HIGH. Integer 1e-7 USD units: pricing.py module header (not re-derived). MEDIUM-HIGH.
5. Conformance rate 3 ALLOW of 4 verdicts = 75.0 %. HIGH. Owners, domains (finance x2, sales x1) and counts are internally consistent (3 agents, 3 tokens, 3 owners). HIGH.
6. "There is no standing production fleet in this repo" and the Production column is an explicit deferral: consistent with the repo (no estate data). HIGH.
PARTLY TRUE
7. "Estate total $1.36": the three per-agent costs sum to $1.355, which the table shows as $1.36 (round half up) while the same table shows $0.675 as $0.67 (the engine floors: `units_to_usd_str`, the C-474 finding). So the displayed per-agent figures sum to $1.35 and the total reads $1.36. This is F-C42-1 (C-474; PR 311 PASS and PR 313 pending decide it, per the cents-rounding question Lane 1 put to Don). Not a new finding. HIGH.
UNVERIFIABLE FROM THE REPOSITORY
8. The Anthropic list prices themselves and the retrieval date: the file cites platform.claude.com/docs/en/about-claude/pricing as retrieved 2026-10-27; an external fact I did not fetch (only the code-to-doc equality is checked).
9. The live telemetry (13 ledger events, 1 open escalation at 82 % of cap, 3 tokens active): needs the stack; only internal consistency checked.
10. "Snapshot 2026-08-11" and "Generated ... from a live FIELD stack": a history statement; the regenerate command (`bash services/ops-console/demo.sh`, `GET http://127.0.0.1:8011/api/overview`) names the console port 8011 and a script that exist (demo.sh present). MEDIUM.

PUBLIC-SAFETY SCAN (all 12 files: agent-estate.md plus 11 capstone-evidence files)
- agent-estate.md: no private or public IPv4, no hostname, no email, no personal or home path, no key shape, no 40-hex id, no flag value, no deploy-state wording. CLEAN (scan and full read).
- field-agent-run.log lines 7, 53, 54: a Windows user path (personal-path class; the C-540 F-C540-2 family). MEDIUM-LOW.
- hardening.md lines 28 and 34: "docker-compose verified on GB10 ... caught at runtime on GB10": the private estate's name as a verification statement; the file is dated history (2026-08-08). Hostname class only if Don rules the estate names are not public (C-561). LOW. Line 106: "Flagged UNTESTED until the repo has a remote": STALE (the repository is public on GitHub, CI runs). LOW-MEDIUM.
- sentinel-scorecard-s2.json line 6 and .md line 3: `engine_commit` "d066218" (a 7-hex commit id of the engine under test). A commit id of the repository's own history, not a build or deploy id of an estate; LOW; keep if the scorecard is meant to be reproducible, since the id lets a reader check out the engine it measured.
- phase-0 to phase-4.md, field-agent.md, v2-one-liners-source.md: no address, hostname, email, key or path. CLEAN. phase-4.md:49 shows "Agents in production (active) 1 agents" (a different dated snapshot from agent-estate.md's 3): not a conflict, two snapshots; neither file labels the date on that line.
CLAIMS (capstone files, read at the places the grep hit): phase-2.md "eight-step" sentinel clause check matches engine order (C-529, C-534 row 3); phase-3.md "tamper-branded post-mortems" and "anti-fabrication citation guard" are the incident-replay and crosswalk features (C-530 row 4); field-agent.md "a bare client 401s where every SDK path succeeds" is consistent with INTEGRATION.md troubleshooting (C-536). Not re-run.

FINDINGS (for cards)
- F-C537-1 MEDIUM-LOW (public-safety, C-560 family): field-agent-run.log:7, :53, :54 personal path: replace with `<repo>`, or regenerate the log from a clean path.
- F-C537-2 LOW-MEDIUM (doc, stale): hardening.md:106 "UNTESTED until the repo has a remote" (it has one; CI runs on it); hardening.md:28 and :34 name the private estate in a verification statement (dated 2026-08-08): date-stamp as history, and (if C-561 rules estate names are not public) generalise.
- F-C537-3 LOW: scorecard `engine_commit` is a repository commit id: decide keep or drop (reproducibility versus the public-safety rule's "no build SHAs"; Don's call, C-561 family).
- F-C537-4 INFO: the $1.355 total versus $0.675 shown as $0.67 is C-474 (already carded); no new card.

CONCLUSION: agent-estate.md is clean and its sums and rates match the code (HIGH). The capstone-evidence folder holds no secret (HIGH, scan); three small items remain (personal path, a stale "no remote" line, estate-name and commit-id wording). I do not know the external list prices or the live figures.
