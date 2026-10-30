VERDICT: PASS WITH CONDITIONS on 1f7f61f51e264566b708e49600bbe6f8b8b80966
(Lane 14, cloud, no GX10: UNVERIFIED re-run. Card: take the Lane 5 verdict C-775 on MCP PR 1 (PR 368), list each condition, check each against the code at file:line, say which block the merge, and the dependence on C-489 (PR 356). PR 368's head is still 1f7f61f (the head Lane 5 reviewed). All four PR commits: author and committer Don Hagell no-reply. CI at this head read by REST now: 7 of 7 jobs SUCCESS (Lane 5 saw them queued). I did NOT run the field-mcp suite (the `mcp` SDK is not installed in this sandbox and I did not install it); everything below is code reading plus probes of the functions it names. PR 369 is now at 1f4fbc7 (Lane 5 read f685e08); PR 356 at a9be069.)

OBJECTIONS FIRST
1. A reviewer's list of conditions is a claim about the code; each one needs a second pair of eyes on the lines, not on the report.
2. "Blocks merge" is a judgement about what the PR promises. This PR promises that no excluded route is reachable from a Tier 1 tool; any path that breaks that promise blocks, whatever its severity label.
3. A coupling that activates by an import-time try/except changes behaviour when another PR merges, with no edit to this one; that deserves a test, not a docstring.

ASSUMPTIONS
A1. Lane 5's numbering: conditions C1-C4 are F-C775-1 to F-C775-4; follow-ups F-C775-5 to F-C775-9. A2. Probes call the named functions with made-up values and stubs; nothing reaches a service.

REASONING (each condition, the code, my verdict)
C1 F-C775-1, a Tier 1 body field reaches an excluded route through the crosswalk: CONFIRMED, BLOCKS.
 - field-mcp catalog.py:44-46: three crosswalk POST tools (`crosswalk`, `crosswalk_markdown`, `pack`) are Tier 1; tools.py:36-54 `_input_schema` applies the segment pattern to `in == "path"` parameters only; a request `body` goes through as the service's own schema, so `agent_id` is an unconstrained string.
 - Crosswalk compliance_crosswalk/api.py:175 (`/pack`: `collect_evidence(req.agent_id) if req.agent_id`), then api.py:210 (`RegistryClient().get_agent(agent_id)`), :227 (`/events?agent_id={agent_id}`), :236 (`/tokens?agent_id={agent_id}`), :237 (`/caps/{agent_id}`): raw f-strings, called with `auth_headers()` (api.py:215-216).
 - My probe of `collect_evidence` with a stubbed transport: `x/../../operator/rotation-state` produces `GET <registry>/agents/x/../../operator/rotation-state`, `<governor>/caps/x/../../operator/rotation-state` and the query forms, each with the perimeter header; `x&limit=1#` injects a query parameter and cuts the rest; `..`, `%2e%2e/x`, a space and a newline pass through raw. HIGH (run). The root is in the crosswalk and field-core clients (same class as my C-683 F-C683-2); the MCP layer is what hands it to a model.
 - Why it blocks: `/operator/rotation-state` is on the excluded list (catalog.py excluded set, the "hash oracle and key fingerprints" routes). A Tier 1 tool must not reach it. Minimal merge fix: constrain the id-like body fields of the three tools with the same segment pattern in field-mcp (a test with a mutant); the service fix (quote path segments, `params=` for queries) is a follow-up card.
C2 F-C775-2, PR 369 refuses a read key on the 7 Tier 1 POSTs: CONFIRMED, DOES NOT BLOCK PR 368; blocks the COMBINATION.
 - authn.py at PR 369's head: line 38 `SAFE_METHODS = {GET, HEAD, OPTIONS}`; line 145 `request.method.upper() in SAFE_METHODS` is the only place a read key is accepted. The seven POST tools (catalog.py:44-46, :52-53, :61-62 per Lane 5) answer 401 under a read key. Needs a ruling (a read-safe POST list in authn, or the POSTs leave Tier 1) before either PR is used with a read key. HIGH (read).
C3 F-C775-3, no overall deadline: CONFIRMED by reading, NOT BLOCKING (follow-up before untrusted upstreams).
 - client.py: `make_client` builds `httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)` (per phase, per read); `Upstream.request` streams and loops `for chunk in resp.iter_bytes(): buf += chunk; if len(buf) > MAX_BYTES: raise` with no clock check. A drip feed is bounded only by MAX_BYTES times the per-read timeout. I did not reproduce Lane 5's 36-second drip (no slow stub run); confidence HIGH from the code. Upstreams are the operator's own internal services (config refuses external hosts), which lowers the severity.
C4 F-C775-4, `--require-hashes` after an unhashed install: CONFIRMED (reading), NOT BLOCKING; blocks the sentence "full closure hash-checked".
 - ci.yml:36-37 installs `packages/field-core[dev]` with dependencies (pydantic and friends) and the 14 services with `--no-deps`; ci.yml:44-45 then `pip install --require-hashes --no-deps -r integration/field-mcp-hashes.txt`. The hashes file has 25 pinned distributions. pip verifies hashes only for what it downloads; a requirement already installed at that version is "already satisfied" and not checked (pip behaviour, general knowledge, MEDIUM; Lane 5 observed it on the GX10: 10 of 25 skipped). Fix: install the hashed file first, or reword.
F-C775-5 (C-489 dependence): CONFIRMED and WORSE than reported. Does not block PR 368; blocks the order "PR 356 first, then 368 unchanged".
 - field_mcp/hosts.py: `try: from field_core.hosts import is_internal_host as _core` (importing PR 356's module when it exists) else a stricter local predicate that refuses every inet_aton spelling. I loaded PR 356's `hosts.py` (a9be069) and compared with `allow_names=False` on 57 spellings: 12 differ, all in one direction: the local fallback refuses, PR 356 accepts (`127.1`, `127.0.1`, `2130706433`, `0x7f000001`, `0x7f.0.0.1`, `017700000001`, `0177.0.0.1`, `10.1`, `167772161`, `192.168.1`, `0300.0250.0.1`, `0x7f.1`). Then I made PR 356's module the active predicate and ran field-mcp's own corpus (test_config.py:11-17): `http://127.1` is in the refused list and is ACCEPTED. So the day PR 356 reaches main, the import-time switch flips field-mcp's behaviour with no edit to this PR, and `test_base_url_refused[http://127.1]` goes red on main. The docstring names a test `test_hosts_predicate` that does not exist; the corpus lives in test_config.py. Needs a policy ruling (are short and numeric spellings of an internal address acceptable?) and a merge order. MEDIUM-LOW.
F-C775-6 (Tier 3 not pinned literally): CONFIRMED. test_route_coverage.py:57 derives the Tier 3 set from the catalog's own excluded table (`w.startswith("Tier 3")`); test_stdio.py:57 holds a partial denylist. A swap edited in the same diff passes. LOW.
F-C775-7 (survivors): PARTLY CHECKED. Dict-key redaction is client.py `_bound` (the `{_bound(str(k), secrets): ...}` line); untested per Lane 5 (not re-run by me). The oauth mapping `token_id -> token` (catalog.py:91, used at tools.py:101) is CORRECT: delegation-authority's introspect reads form field `token` (api.py:437). So K09 is an untested-but-right mapping. LOW.
F-C775-8 (jsonschema, comment): CONFIRMED. tools.py:14 imports jsonschema; services/field-mcp/pyproject.toml dependencies are field-core, httpx, mcp only; integration/build-constraints.txt header says "all 17 pyproject.toml files"; the tree has 18. LOW.
F-C775-9 (two authority-bearing reads): Don's call, unchanged.
NEW, mine:
F-C790-1 (LOW): client.py `SEGMENT = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9._:@+~-]{1,200}$")` is applied with `.match`; `$` also matches before a trailing newline. Probe: `"a\n"` is accepted and builds `/agents/a%0A` (quoted, no injection, but the receiver gets an id with a newline); `"..\n"` and `".\n"` are refused by the lookahead. Use `fullmatch` (and `\Z` in the schema pattern). PROVEN.
F-C790-2 (info): CI is 7 of 7 green at the head; Lane 5's "queued" is superseded.
Public repo: nothing in the diff I read holds an estate address, flag value, build SHA, deploy status or credential; probes here use reserved names.

WHICH BLOCK THE MERGE (my call)
- Blocks: C1 (F-C775-1), at least for the three crosswalk POST tools; and the wording fix for C4 (the PR must not say the whole closure is hash-checked).
- Does not block PR 368, needs a ruling or an order first: C2 (before PR 369 and PR 368 are used together), F-C775-5 (before PR 356 merges), C3 (before an upstream that is not trusted).
- Follow-ups: F-C775-6, -7, -8, -9, F-C790-1.

CONDITIONS
C1 (blocks): constrain body id fields, with a mutant; open the service card.
C2: ruling on the read key and the 7 POSTs.
C3: ruling on inet_aton short forms and the merge order of PRs 356 and 368; fix the docstring's test name.
C4: the wording on hashes, or the install order.
Not verified: the field-mcp suite (not run); any behaviour with the real MCP SDK; Lane 5's 36-second drip and its mutant table (not re-run); the full GX10 set.

CONCLUSION
Lane 5's conditions hold against the code. F-C775-1 is real and I reproduced the root in the crosswalk; it blocks the three crosswalk POST tools. The C-489 coupling is stronger than the report says: the fallback and PR 356 disagree on 12 spellings and one of them is in field-mcp's own refused list, so PR 356 landing turns this suite red by itself. PASS WITH CONDITIONS on 1f7f61f: C1 blocks.
