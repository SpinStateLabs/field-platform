gx10 verifier A, C-1201: per-suite pass-count ledger, main at MERGE 15 (baseline) and MERGE 16 to 23. No push.

METHOD (read this first): I did NOT check out each main sha and re-run. For every one of these mains the coordinator gate was a full 16-suite GX10 run on a head EQUAL to the main sha, so I took the counts from those eight existing reports (HIGH for the transcription, each report re-read just now). That is the same GX10 and venv (Python 3.12.3), one run per sha. It is not an independent re-run: if a run was wrong, this ledger repeats the error. A fresh scratch-worktree set (8 full runs, about 2 hours of GX10, one at a time) can follow on request.

Sources by MERGE: 15 = my C-1135 run (05942b98); 16 = B 20261102-2335 pr446 (4f731ee9); 17 = A 20261102-0605 cb25 (40aec372); 18 = B 20261103-1205 cb26 (b39287c1); 19 = B 20261103-1310 pr442 (6385f877, a merge commit whose second parent is main b39287c1); 20 = B 20261103-1430 pr461 (cddca526); 21 = B 20261103-1920 cb28 (c356e205); 22 = B 20261103-2215 pr470 (4ef319cc); 23 = B 20261103-2745 s2q (793481f3). All 0 failed in every run. Skips constant: core+sealed-ledger 4, tools 4, compliance-crosswalk 5.

LEDGER (passed counts; columns M15 M16 M17 M18 M19 M20 M21 M22 M23):
core+sealed-ledger: 2346 2346 2346 2346 2346 2346 2346 2346 2350
tools: 3749 3749 3762 3771 3772 3772 3776 3794 3794
field-agent: 207 207 207 207 207 207 207 207 207
agent-registry: 306 306 306 306 311 311 311 311 311
attestation-reporter: 221 255 255 255 255 255 255 255 255
claude-approver: 315 315 315 315 315 315 315 315 315
compliance-crosswalk: 369 369 369 369 369 369 369 369 369
conformance-sentinel: 263 263 263 263 263 263 263 263 263
delegation-authority: 252 252 256 256 256 256 257 257 257
federation-broker: 188 188 188 188 191 191 191 191 191
force-gateway: 448 448 448 448 448 448 448 448 448
incident-replay: 97 97 97 97 97 97 97 97 97
kill-switch: 242 242 242 242 242 242 242 242 242
lifecycle-manager: 267 267 269 269 269 269 269 269 269
ops-console: 457 457 457 457 457 457 457 457 457
spend-governor: 291 291 291 291 291 291 291 291 291

FINDING: none. No suite went DOWN between any two consecutive mains. Rises only: attestation-reporter +34 at 16 (PR 446); tools +13 at 17, +9 at 18, +1 at 19, +4 at 21, +18 at 22, 0 at 23; delegation-authority +4 at 17, +1 at 21; lifecycle-manager +2 at 17; agent-registry +5 at 19; federation-broker +3 at 19; core +4 at 23. Every other cell is flat. (Which PR added which count is not itemised here; the +34 at 16 is the PR 446 attestation-reporter tests by its title, MEDIUM.)

NOTES (MEDIUM to LOW): the tools suite rises at 17 to 22 are plausible from the pin-test and lint-test PRs landed in those merges but I did not itemise them. Kill-switch stays at 242 through MERGE 23 on main, while batch m1b (PR 476 on 793481f3) showed 270: PR 476 is not on main yet. A flat count can hide one test removed and one added; only a drop shows in this ledger. Counts are of passed tests, so collected tests that were skipped or deselected are not visible beyond the three constant skip counts.
