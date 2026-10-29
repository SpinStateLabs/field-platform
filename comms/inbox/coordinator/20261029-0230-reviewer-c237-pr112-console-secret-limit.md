# C-237 reviewer report (Lane 5): PR 112 docs/ops-console-secret-limit-c228 @39774a81d31aaad01d916abedf4269369579f0ae

VERDICT: PASS on the exact head 39774a81d31aaad01d916abedf4269369579f0ae. The new Declared row says what the console page does, with correct line references, and matches the ruling D-29 ("document now, gate later"). Full gx10_verify is green on the head.

OBJECTIONS FIRST
1. A Declared row documents a weakness; it does not close it. Until the gate exists, a shared secret typed on a plain-http, non-loopback page crosses the network in clear on every request and poll. The row says so, and says the gate follows; the date or condition for "follows" is "once no operator is known to use plain http (D-29)", which depends on a confirmation not yet given. [HIGH]
2. The row cites `console.html` line numbers (:745, :780, :826). Line numbers rot when the file changes; they are correct today (below) and PR 115 and the others do not touch console.html. A later console edit makes them stale. LOW. [HIGH]
3. I read the page code, I did not run the page in a browser over plain http to watch the request. [HIGH]

ASSUMPTIONS
1. PR is one commit on main 10fb197 (merge-base equals that main), author and committer Don Hagell noreply, one file services/ops-console/README.md, one insertion. D-29 is in tasks/DECISIONS-FOR-DON.md on comms: "document now, gate later: a README declared-limit line ... (card C-228); the gate follows when you confirm no operator uses plain http." [HIGH]

REASONING
1. The row: "The shared secret typed into the console is protected in transit | Declared only | the operator key is refused unless the page is https or loopback (a secure context); the shared perimeter secret (`x-field-auth`, `console.html` :745, :780, :826) has no such gate: it is kept in `sessionStorage` and sent with every request, so over plain http to a host that is not loopback it travels in clear. Use https or loopback. A gate like the operator key's follows once no operator is known to use plain http (D-29)". It sits in the README's Enforced-vs-Declared table beside the existing row about the secret ("browser prompts for the secret (kept in sessionStorage)"). [HIGH]
2. Code check (console.html at main, unchanged by any open PR): line 745 `let SECRET = sessionStorage.getItem("field-secret") || "";`; line 780 inside `hdrs()`: `if (SECRET) h["x-field-auth"] = SECRET;` with no transport test; line 826 inside `saveSecret()`: `sessionStorage.setItem("field-secret", SECRET);`. `hdrs()` is the single header builder used by `api()`, the live stream, the manifest read, the export and the Setup area, so "sent with every request" is accurate. The operator key, by contrast, is gated by `keyTransportOk()` (lines 757-790) and refused unless the page is https or loopback, as the row says. [HIGH, read]
3. The statement "over plain http to a host that is not loopback it travels in clear" follows: nothing in the page encrypts the header, and `fetch` to a same-origin http URL sends it as typed. [HIGH]
4. Consistency with the ruling: D-29 (PROVISIONAL, MEDIUM; my C-200 finding 3) ruled "document now, gate later" and named this card; the row's last sentence repeats the condition. No other README row claims the secret is protected in transit (grep of the ops-console README for "secret", "https", "loopback": the other hits are the Enforced row about the locked API and the operator-key row). [HIGH]
5. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr112): core_services 2209 passed 4 skipped; tools 1925 passed 3 skipped; agent-registry 238; sentinel 111; incident-replay 91; crosswalk 162 (1 skipped); gateway 210; lifecycle 185; attestation 66; ops-console 171; approver 101; field-agent 118; topology_lint OK. VERDICT CI-EQUIVALENT STEPS GREEN. [HIGH]
6. Public-repo hygiene: the row names no address, host or flag value; it describes the code. [HIGH]

CONCLUSION
PASS on 39774a8. Optional: replace the three line numbers by function names (`hdrs()`, `saveSecret()`) so the row does not rot; keep D-29 as the tracking id.

What I did NOT do: observe the request in a browser over plain http; check the other docs (STATE.md, runbooks) for a statement that the console secret is protected in transit.
