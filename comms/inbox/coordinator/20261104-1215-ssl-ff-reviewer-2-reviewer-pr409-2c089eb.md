# Reviewer report: PR 409 @2c089ebb (field-agent SDK transport caps the reply bytes it reads, C-642b; stacked on PR 372)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator). Scope: the top commit only (2c089ebb, `packages/field-agent/src/field_agent/_transport.py` +36/-3 and `tests/test_read_cap_c642b.py` +103). The three commits below it are PR 372's head 1b8f9e3f (the GitHub base of this PR is `fix/upstream-error-field-agent-c642`, whose head equals that commit); I did not review them here.

## Verdict: PASS WITH CONDITIONS (head 2c089ebbb799c9b639309d33cb29889fa66fac61)
Conditions: C1 add a test with a body delivered in several chunks whose total exceeds the cap, each chunk below it (mutant S3, F1 below): as written, a transport that resets its running total per chunk passes every test, and real httpx streams in chunks well under 1 MiB, so the cap would not bind on real traffic (HIGH, run). One test, no code change. C2 rebase: the stack base (PR 372) conflicts with main 97dcfec1 in `docs/ENVIRONMENT.md` and `packages/field-agent/src/field_agent/liveness.py` (`git merge-tree`), so PR 372 must be rebuilt first and this commit re-applied on it. C3 GX10 16/16 on the exact rebased head; C4 CI green. No code defect found in the transport itself.

## Objections first
1. The cap VALUE is unpinned: the tests use `t.MAX_RESPONSE_BYTES` as the boundary, so 1 MiB, 1 MiB + 1 or 10 MiB all pass (C1, C2, C4 below, also surviving the whole field-agent suite). The commit message says "1 MiB" (HIGH, run).
2. The streaming path is not distinguished from the no-stream fallback: forcing the fallback always (F3) passes the full suite, because the fallback also refuses an oversize body after buffering it. A client that buffers the whole reply, the thing the cap is meant to prevent, is therefore not caught (HIGH, run). Mitigation: a test that raises mid-iteration after the cap, asserting that later chunks are never pulled.
3. `iter_bytes()` counts decoded bytes (S2 killed), so a gzip bomb is bounded (HIGH, run). Good.
4. The rebuilt `httpx.Response` drops content-length, content-encoding and transfer-encoding so the already-decoded body is not decoded twice; keeping them (S7) passes all tests, so the reason for dropping them is not pinned (MEDIUM, run).
5. `ResponseTooLarge` is a plain `Exception`; callers wrap it (heartbeat, usage, pinned by the tests) but other SDK clients that call `AuthedClient` and catch only `httpx.HTTPError` would not catch it (MEDIUM, reasoned; I did not enumerate every caller).
6. The auth header merge and the HTTP verb on the streamed call are pinned only by older tests in the suite (S8, S9, V1, V2 failed there: 2, 26, 4 and 72 tests), not by this PR's file (HIGH, run). Fine, but the PR's file alone would not notice.

## Scope and identity
4 commits in the PR, 13 files in the whole stack; the top commit touches 2. Author AND committer on all four = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py` is absent at this stack base, so I did not run it.

## Runs
Baseline (unmutated head): test_read_cap_c642b.py 8 passed; the full field-agent suite 211 passed, 1 skipped, with one subprocess test (`test_canary_agent.py::test_the_process_never_exits_on_a_halt`) failing in my environment with `No module named field_agent`; the same test fails identically on the parent commit 1b8f9e3f, so it is environmental (it spawns `python -m field_agent.canary` without my path). I deselected it for survivors' full-suite runs. Mutants edit `_transport.py` one at a time; kill = the PR's file fails; for survivors I also ran the full suite; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | PR file | Full suite |
|---|---|---|---|---|
| C1 | cap value | 1_048_577 | SURVIVED | SURVIVED |
| C2 | cap value | 1_048_575 | SURVIVED | SURVIVED |
| C3 | cap boundary | streaming `>=` (exactly cap refused) | KILLED | n/a |
| C4 | cap value | 10 MiB | SURVIVED | SURVIVED |
| S1 | streaming | check removed | KILLED | n/a |
| S2 | streaming | counts raw, not decoded, bytes | KILLED | n/a |
| S3 | streaming | running total reset per chunk | SURVIVED | SURVIVED |
| S4 | streaming | body not kept | KILLED | n/a |
| S5 | streaming | status forced 200 | KILLED | n/a |
| S6 | streaming | all headers dropped | KILLED | n/a |
| S7 | streaming | framing headers kept | SURVIVED | SURVIVED |
| S8 | streaming | auth headers not sent on the streamed call | SURVIVED | KILLED (2 failed) |
| S9 | streaming | verb forced to GET | SURVIVED | KILLED (26 failed) |
| F1 | no-stream fallback | check removed | KILLED | n/a |
| F2 | no-stream fallback | `>=` | KILLED | n/a |
| F3 | no-stream fallback | fallback always taken | SURVIVED | SURVIVED |
| R1 | refusal text | cap not named | KILLED | n/a |
| R2 | refusal text | body bytes in the cause chain | KILLED | n/a |
| V1 | verbs | patch sent as get | SURVIVED | KILLED (4 failed) |
| V2 | verbs | post sent as get | SURVIVED | KILLED (72 failed) |

Counted from the table: 20 rows (cap 4, streaming 9, fallback 3, refusal 2, verbs 2). By the PR's file alone: KILLED 10, SURVIVED 10. With the full suite: KILLED 14, SURVIVED 6 (C1, C2, C4, S3, S7, F3), none equivalent in my reading. Kill rate by the PR's file 10 of 20 = 50%; combined 14 of 20 = 70%. Per behaviour (PR file alone): cap 1/4, streaming 5/9, fallback 2/3, refusal 2/2, verbs 0/2.

## Findings
- F1 MEDIUM (HIGH confidence, run): S3. Condition C1. Without a multi-chunk test the headline protection (a peer streaming gigabytes in 64 KiB chunks) is untested.
- F2 MEDIUM: C1, C2, C4, the 1 MiB value. Assert `t.MAX_RESPONSE_BYTES == 1_048_576` or test with a literal.
- F3 LOW to MEDIUM: F3, objection 2, no test proves the streaming path stops reading after the cap.
- F4 LOW: S7, objection 4.

## Not verified
Rebase on 97dcfec1 (stack base conflicts); CI; GX10; the three PR 372 commits beneath this head; real network behaviour (all tests use MockTransport).
