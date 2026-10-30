VERDICT: PASS WITH CONDITIONS on 50c87b9f0924a407ddb62b665323df84b1850a24 (UNVERIFIED: cloud reviewer, no GX10, CI not read; probes ran in-process against the real app; the PR's own tests were run under C-701)

Head matches the card (same head as the C-701 report; this is the information-leak angle only). One commit on main; author and committer are the no-reply identity. Files read: delegation_authority/api.py introspect and oauth/introspect handlers.

OBJECTIONS FIRST
1. The JSON route POST /introspect distinguishes an unknown token from a revoked one, PROVEN, in body: both answer 200 with status "revoked" and active false, but an unknown id returns a fixed reason ("unknown token id — treated as revoked (fail closed)"), no agent_id, an empty scope list and no issuance time, while a real revoked token returns reason "token is revoked" plus its agent_id, scope, expiry and issuance time. So anyone holding the perimeter secret and a token id can (a) tell a real revoked or expired token from an invented id, and (b) read the agent, scope and expiry of a revoked or expired token. Token ids are uuids so guessing is impractical; the exposure is for a caller who already has an id (a log line, a ledger row) and learns the agent and scope behind it. MEDIUM-LOW.
2. The form route POST /oauth/introspect does NOT leak: revoked, expired and unknown all answered exactly {"active": false}, status 200, and the same body bytes (PROVEN, three of three); the README states this as a choice. The two routes therefore have two different disclosure policies for the same question. LOW-MEDIUM (inconsistency; the strict one is the form route).
3. Timing: no distinguishable difference on either route in my probe (1,500 calls per state; form route medians 2,719 us revoked, 2,732 us expired, 2,760 us unknown, 2,816 us active; JSON route 3,009 / 3,080 / 3,037 / 3,178 us; 95th percentiles overlap). All states do one store read. An active token is slightly slower (more fields to build), which is the intended answer anyway. Not a finding.
4. Ids echoed: the JSON route echoes the caller's own token id in the answer (any string, including markup, as data in a JSON body); the revoke route answers 404 with "token '<id>' not found" and the id is reflected without a length limit (a 5,000-character id produced a 5,031-character reply). The ids are the caller's own input, not another party's; the reflection is in JSON, so markup is not executed. LOW.
5. Validation errors on the JSON route echo the offending input back (the framework default: "input": 123 for a wrong-typed id; the whole body for a missing field). The registry service in the same repository strips values from its validation errors (a helper named validation_errors_without_values is used in registry api.py:186); delegation-authority does not for this route. For an id field the value is the caller's own and not a secret; if a token or key were ever pasted into the field it would be reflected. LOW.
6. The 400 for a blank form field and the 422 for a missing JSON field are distinguishable from the 200s by status, as expected for malformed input.

ASSUMPTIONS
A1 "Differ" means any observable difference in status, body keys, body text or response time between an unknown id and a revoked id. A2 Probes used the in-process app, a real token store and registry/ledger stubs of the PR's own fixture; one expired token was made by editing the stored expiry. A3 Timing medians on one machine; sample size 1,500 per state.

REASONING
1. Body probe (status; keys present): JSON route, active: 200, keys active, agent_id, expires_at, issued_at, scope, status, token_id. Revoked: 200, adds reason "token is revoked", status revoked. Expired: 200, reason "token is expired", status expired. Unknown: 200, keys active, reason, scope, status, token_id; status revoked; reason "unknown token id ... (fail closed)"; agent_id null. Form route: active: 200 with scope, scope_list, sub, client_id, token_type; revoked, expired, unknown: 200 and exactly {"active": false}. HIGH.
2. The handler code agrees: introspect() builds the unknown answer from a fixed branch and the known answer from the stored row (api.py introspect, the TokenNotFoundError branch); oauth_introspect returns {"active": False} for not found, and for a non-active token (read from the handler's docstring, which lists "revoked, expired and unknown all return exactly {active: false}"). HIGH for the route probed.
3. Timing probe as in objection 3: differences between revoked, expired and unknown are about 1.5 percent of the median, inside the spread. HIGH for this machine and this size; a remote network adversary would see less.
4. Echo probes as in objections 4 and 5. HIGH.
5. Diff scan of the PR for leak-relevant changes: the only introspection change is the exact (unpadded) id match on the form route, which removes a second spelling for one id. No new echo. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The form route is a clean oracle-free answer; the JSON route discloses existence and the agent and scope of a revoked or expired token to a holder of the perimeter secret and an id. Conditions, none blocking this PR:
- C1 F-C712-1: decide whether the JSON route should return the same minimal answer for revoked, expired and unknown ids as the form route, or whether the richer answer is wanted for operators (then restrict it to the operator path or say so in the README).
- C2 F-C712-2: strip input values from the JSON route's validation errors as the registry does; bound the id length reflected by the revoke route's 404.

FINDINGS
F-C712-1 MEDIUM-LOW, services/delegation-authority/src/delegation_authority/api.py (introspect: the TokenNotFoundError branch versus the stored-row branch). PROVEN.
F-C712-2 LOW-MEDIUM, same file (two routes, two disclosure policies). PROVEN.
F-C712-3 LOW, same file (revoke 404 reflects an unbounded id; JSON 422 echoes the input). PROVEN.
F-C712-4 INFO, timing: no difference found. MEDIUM (one machine).

NOT VERIFIED: network-level timing; whether the perimeter secret is the only guard in front of /introspect on the estate (read, not checked); CI; the rest of the delegation-authority suite beyond the C-701 run.
