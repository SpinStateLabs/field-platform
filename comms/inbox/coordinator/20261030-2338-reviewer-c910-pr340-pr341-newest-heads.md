VERDICT: PASS on 25ffdc11022c6b8ae655fef5d3b4548499aebe3a (PR 340) and PASS on 67fefb514ac284fff8f0496495913306e45be910 (PR 341); one non-blocking note on each

PR 340 head: 25ffdc11022c6b8ae655fef5d3b4548499aebe3a
PR 341 head: 67fefb514ac284fff8f0496495913306e45be910

Reviewer Lane 15, cloud-reviewer, C-910. UNVERIFIED: no GX10, CI not read; docs read against source, scratch-tree test runs.

## Objections first
1. PASS is for the deltas I was asked about (builder C-767 on PR 340, C-768 on PR 341) and my own earlier conditions; it is not a claim that INTEGRATION.md is complete. A document of this kind can always be one more cause short (HIGH on what I checked, MEDIUM that nothing else is missing).
2. Line citations are time-bound. PR 340 cites `api.py` lines that are exact against the PR's own base, not against current main: against main the F1 handler block starts about two lines earlier than the cited 887 (my read: main's line 887 is the last comment line of the block, the first ordinary line of the block is 884-885), so the range 887-910 still contains the handler but starts mid-comment (HIGH on the read, LOW in impact). The doc already says its cites were read against an older main and must be re-checked.
3. Where the builder said "no named person or company in the diff": true of the diff. The same names remain in two other places at both heads, outside these PRs: the roster example manifest (manifests/doa-roster.example.yaml, 1 line) and docs/IMPLEMENTATION.md (1 line). The builder named both as a suggested card; I confirm both (HIGH, count at the head). Tree-wide the author name appears in 71 tracked files at PR 340's head, mostly as a decision owner or contact; not this PR's scope and not re-judged.
4. The refusal text for an unreachable sentinel includes the sentinel's base URL (api.py:358-375 builds "sentinel unreachable at <base>: ..." and `_authorize` puts it in the 503 detail returned to the caller). Not in these diffs and not documented as such; it is an address disclosure to a caller, internal in typical use (MEDIUM, read, not probed).

## PR 340 (docs/INTEGRATION.md; delta bde88a2 to 25ffdc1, one commit, 10+/6-)
- C-767 F-1 (403 and 503 descriptions incomplete): CLOSED. New text lists 403 body fields `decision`, `clause_id`, `reasons`, `agent_id`, `action`, escalation flag, and `retry_after_seconds` when supplied; 503 causes "for example" plus a non-JSON body and a reply with no verdict. Each matches `_authorize` and `SentinelClient.check` at the PR head (body dict built at api.py:551-585; SentinelUnavailable for "non-JSON body" and "no verdict" at 358-375) (HIGH, read).
- F-2 (named person and company in the roster example): CLOSED in the doc: the example now uses placeholder grantor and org (HIGH, diff). The related example file still names (objection 3).
- F-3 (docstring citation only): CLOSED: docstring `api.py:41-43` is now accompanied by handler `887-910`, `_authorize` `551-585`, `SentinelClient.check` `358-375`; at the PR's own base each range lands on what it names (HIGH, read); see objection 2 for main.
- Earlier: the pre-v1.2 kill-switch "405" sentence (C-652 F-C652-5) remains at docs/INTEGRATION.md:232-234; neither delta nor builder claims it; my C-767 did not list it as a condition. Noted, not a condition.
- Public-safety sweep of the added lines: addresses 0, flag values 0, deploy-status words 0, e-mail 0, home paths 0, one hex token (the cited main commit id, a code-history id, already present in the prior head) (HIGH, count).
- Test touching this doc: tools/tests/test_deploy_docs.py 35 passed. merge-tree: no conflict with main, 341, 337, 338, 339, 342, 352, 379, 381, 383.

## PR 341 (docs, force-gateway; delta b6f9b61 to 67fefb5, three files, 4+/3-; vs merge base: 14+/5- including api.py)
- C-768 F-1 (README:337 owner notification): CLOSED: now "the gateway.bypass ledger record (the gateway sends no owner notification; see ADR 10, note 1)" (README.md:337-338) (HIGH).
- F-2 (ADR line 67 versus note 4): CLOSED: line 67 reads "1 or another accepted spelling, see note 4"; note 4 (:85) lists the spellings and cites `api.py:290-301`, which at the head is `_posture_flag` (HIGH, read).
- F-3 (range omits :688): CLOSED: now :669-688, which includes the judge-call error branch (`_count(... "error" ...)` at the end of the range) (HIGH, read).
- F-4 (note depends on a file in another repository, no pin): NOT DONE, builder says so; INFO.
- api.py is still comment-only: the syntax trees at the merge base and at the head are equal once docstrings are dropped (3 lines out, 3 in; HIGH, run). No change to api.py since the previously reviewed head b6f9b61 (diff of services/force-gateway/src: empty).
- Tests: the two tools test files naming ADR 10 or the gateway README plus the force-gateway suite: 443 passed (HIGH, run).
- Public-safety sweep of the added lines: addresses 0, hex 0, deploy-status words 0, e-mail 0, home paths 0 (HIGH, count).

## Authorship
Author and committer: the no-reply Don Hagell identity on every commit of both PRs (read from the log).

## Conditions (all non-blocking)
1. Open the card for the other two files that name a person (objection 3).
2. Decide whether to scrub the sentinel base URL from the 503 text (objection 4) and whether to note it in the doc.
3. Re-check the line cites after the next force-gateway change (objection 2).
Merge order: independent; each merges clean with the other and with every PR I tried.

Not verified: CI, GX10, behaviour of the 503 text at runtime, the pre-v1.2 kill-switch sentence.
