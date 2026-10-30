# C-538 (Lane 9, cloud-reviewer, read-only, no GX10): docs/VIDEO-SCRIPT.md (187 lines) against main b929f12

VERDICT: the script's spoken claims are accurate except two stale or inconsistent numbers. Of 24 statements checked: 19 TRUE, 3 STALE or INCONSISTENT, 2 UNVERIFIABLE without running the demo. Every file, command, console label, error message and kill-drill figure it names exists in the repository or its evidence. No estate value, address, hostname, path, key, flag value or deploy status in the file (scan and read). No secret read or printed.

OBJECTIONS FIRST: (1) a spoken script says numbers aloud, so "approximately right" is not enough; I checked each number against source or evidence, not against a fresh run (no stack here). (2) The demo's event count and timings change from run to run, so a script that states them fixes a snapshot. (3) The Enforced-vs-Declared claim ("every service ships a table") is a count I could make; the quality of each table I did not judge.

TRUE
1. Scene 1: the manifest integration/demo/manifests/invoicing-agent.yaml exists and holds `kill_switch:` (line 30), `spend_cap:` (36), `delegation:` / `scope:` (64, 66). HIGH.
2. Scene 2: `bash integration/demo/run_demo.sh` boots seven services: registry 8001, ledger 8002, delegation 8003, governor 8006, sentinel 8004, killswitch 8005, replay 8007 (run_demo.sh:30-41). HIGH.
3. Scene 2: the spend cap is USD 500 a day from the manifest with escalation at 80 percent (run_demo.sh:67); the token is minted with `--ttl 3600` (one hour) and scopes "read timesheets" and "draft invoices" (run_demo.sh:76). HIGH.
4. Scene 2: "the fifth draft arrives with the meter at ninety-six percent of cap ... ESCALATED E.spend_threshold" and "transfer funds BLOCKED D.scope": invoicing_agent.py:30-31 (5 drafts x $120 against $500 = 96 percent), clause names in field-core conformance.py and sentinel engine.py (E.spend_threshold at :637, D.scope at :561-565). HIGH.
5. Scene 2: "kill confirmed in about forty milliseconds, verified and restored in under sixty": docs/capstone-evidence/phase-3.md:49 records kill confirmed 39.16 ms, heartbeat 41.26 ms, total 52.84 ms, restored. HIGH for that snapshot. (Another recorded run, ADR 02 and STATE.md, shows 20.45 ms / 22.41 ms; the script's claim is true of the committed evidence, not a guarantee.)
6. Scene 2: "every check written to a tamper-evident ledger": the sentinel appends every outcome (engine.py:243-262, best-effort for BLOCK/ESCALATE per C-529 row 16). MEDIUM-HIGH.
7. Scene 3: `bash services/ops-console/demo.sh` exists; the console is at 127.0.0.1:8011; the UI has the harness form with a button labelled "ask the sentinel" (console.html:313, :321), a KILL agent control (:889, :947) and a "resolve" control (:987). HIGH.
8. Scene 3: "every button goes through the same services, with your name recorded on the ledger; delete the dashboard and the governance model doesn't change": the console proxies to the services and sends operator identity on guarded writes only (PR 288 and PR 299, C-523 re-audit: the operator pair reaches an upstream only from the 7 guarded write routes). MEDIUM-HIGH.
9. Scene 4: integration/video/stage_scene4.sh and integration/video/CUE-CARD.md exist. HIGH.
10. Scene 4: the exact verify strings in the cue card match the code: "OK - chain intact over N events" (sealed-ledger cli.py:310, :396), "TAMPERED - hash mismatch at index N: stored ... != recomputed ... (record was mutated)" (field-core ledger.py:223), "ANCHOR FAILURE - ... history was REWRITTEN" (sealed-ledger anchors.py:183, tested in test_sealed_ledger.py:157). HIGH.
11. Scene 4: "a signed fingerprint of the chain, stored off the box ... the forgery passes the naive check and fails the anchor": the anchors design (README, C-186, C-520: `verify --anchors` checks the live chain against anchors; C-520 notes it does not detect removal of the newest anchors, which the script does not claim). HIGH.
12. Scene 5: "every service ships an Enforced vs Declared table": 14 of 14 service READMEs carry one (grep of services/*/README.md). HIGH.
13. Scene 5: the board pack: `attest render --out "$OUT/board-pack" ... --no-pdf` (run_demo.sh:121), board-pack.json read back at :125; the HTML name `board-pack.html` is the script's own path (not re-grepped in the attestation source in this pass). MEDIUM.
14. "Humans organize; AI operates." and the close card text: README.md:9. HIGH.
15. Production brief: Tone, 4:00 length, 60-second cut table are production directions, not claims. n/a.
16-19. The recording notes (hide personal paths with `PS1`, label synthetic data, do not speed up the drill, re-run rather than edit) are consistent with the public-safety rules. HIGH. The prep step "`bash services/ops-console/demo.sh` ready in a second terminal" and "browser at http://127.0.0.1:8011/" are the console demo's documented address. HIGH.
STALE OR INCONSISTENT
20. Scene 5 closing line: "one hundred sixty-eight tests": the repository collects 8,308 tests on main (C-499 recomputed it) and docs/IMPLEMENTATION.md says 209 for an earlier gate; 168 is an August figure. A number said aloud on camera and wrong. HIGH. Fix: drop the count or say "thousands of tests" with the CI source, or read the current CI figure.
21. Scene 2: "Fifteen events. One hash chain. Intact.": `run_demo.sh:111-112` prints the number it finds (`{n} events, chain intact: {ok}`); other docs show 13 (agent-estate.md) for a different snapshot. The script fixes a number the run does not guarantee. MEDIUM. Fix: say the number on screen.
22. The 60-second cut says "TAMPERED at index 2" while Scene 4 and the cue card show "hash mismatch at index 0". LOW; make the two agree.
UNVERIFIABLE WITHOUT RUNNING
23. "the run takes ~23 s": agrees with docs/IMPLEMENTATION.md (~23 s) but not docs/INTEGRATION.md (~30 s, C-577).
24. "kill confirmed ... verified and restored" on the machine that records: timings vary; see row 5.

PUBLIC-SAFETY: no IPv4 other than loopback, no hostname, no email, no personal or home path, no key, no flag value, no deploy status. CLEAN.

FINDINGS (for cards)
- F-C538-1 MEDIUM (doc, spoken number): row 20: replace "one hundred sixty-eight tests".
- F-C538-2 MEDIUM-LOW (doc): row 21: do not state the event count aloud; show it.
- F-C538-3 LOW: rows 22-23: make the 60-second cut agree with the cue card; reconcile the ~23 s / ~30 s demo timing across IMPLEMENTATION.md, INTEGRATION.md and this script.

CONCLUSION: the script matches the code and the evidence on every command, label, message and measured figure I could check (HIGH), and is public-safe (HIGH). Two spoken numbers are wrong or fragile: the test count and the event count (HIGH for the first). I do not know what the next run prints.
