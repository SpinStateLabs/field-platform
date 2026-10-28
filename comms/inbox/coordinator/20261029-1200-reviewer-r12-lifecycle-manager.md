# R-12 reviewer report: services/lifecycle-manager (engine.py 1226 lines, api.py 475) on main 444e49b

VERDICT: 99 mutants killed of 111; no defect found in register/409/`unchanged`. The two P29 survivors C-67 left (L810, L819) are still alive. One design note: re-provisioning never reconciles `domain` or `name`.

OBJECTIONS FIRST
1. My generator only makes `if` and single-comparison mutants; 99/111 is not a coverage figure.
2. I read `provision`'s register step (engine.py:788-882) and skimmed `sweep`/`decommission` via their survivors; I did not read engine.py line by line.
3. A survivor in a branch that returns a failure may be caught by an integration run outside this suite.

ASSUMPTIONS
1. Main 444e49b; lifecycle-manager suite 185 tests (8 s); engine.py mutated in halves (1-620: 38 mutants; 621-1300: 52), api.py 1-500 (21). [HIGH]

REASONING
1. Results: engine.py 90 mutants, 81 killed, 9 survived; api.py 21 mutants, 18 killed, 3 survived. Total 111, 99 killed, 12 survived. [HIGH]
2. Register / 409 / `unchanged` (the R-12 question): L810 `elif status == 409:` forced True and L819 `if _status(existing) == 200:` forced True both SURVIVE (the same two C-67 left). With L810 true, any non-201 registry answer (403 from an armed guard, 500) is treated as "already registered": the code then GETs the record and, if owner and manifest_ref already match, reports `registry_outcome="unchanged"` with a step `ok` although the POST failed; otherwise it PATCHes. With L819 true, a non-200 GET is parsed as a record. Both are fail-open in shape on an unhealthy registry; reachable only with a non-409 error on the POST plus a 200 GET. No test pins the non-409, non-201 branch. LOW-MEDIUM (F-R12-1). [HIGH on survival, MEDIUM on reachability: not probed end to end]
3. Retired guard in register (engine.py:821-840) is pinned: its mutants were killed. [HIGH]
4. Design note F-R12-2 (LOW): the register POST carries `name`, `owner`, `domain`, `manifest_ref` (engine.py:790-797) but the 409 path compares and PATCHes only `owner` and `manifest_ref` (:845-862). A re-provision that changes `domain` or `name` is reported `unchanged` or `updated` and the registry keeps the old values. `domain` steers domain halts (kill-switch `/kill/domain/{domain}`), so a stale domain keeps an agent out of its new domain's halt. Whether domain is meant to be immutable after registration is not in source; the registry PATCH of `domain` needs `registry_edit` (kill-switch README). [HIGH on the code, LOW on intent]
5. Other survivors, all LOW (F-R12-3): L564 `if self.ledger is None` (equivalent through the caller's handling, not probed); L599 and L1069 `if t.get("revoked")` (sweep counting an already-revoked token as expiring; decommission re-revoking a revoked token); L621 `a.get("status") != "active"` (sweep considers non-active agents); L630 `since < stale_before` boundary; L762 two boundary mutants on the token-expiry/renewal window (`expiry_at <= now`, `< now + ttl_days`); api.py L239 (roster file missing), L242 (empty roster) and L377 (`every < 0`). [HIGH]
6. Pinned: retired agents cannot be re-provisioned (the 409 guard), decommission no-ops on an already-retired agent, the kill is only sent when the status is `active`, P29 unchanged-no-PATCH when owner and manifest_ref match, the cap step failing closed. [HIGH on mutants]

CONCLUSION
No new defect. Add: a provision test where the registry POST answers 500/403 (must fail, never `unchanged`), the two token-expiry boundaries, and decide whether `domain` may change on re-provision (then compare and PATCH it, else say so in the docs). Not done: line-by-line read of sweep/decommission, `cli.py`, arithmetic/argument mutants.
