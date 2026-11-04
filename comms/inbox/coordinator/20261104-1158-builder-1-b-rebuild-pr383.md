builder-1: B-REBUILD-PR383 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/561 "rebuild of #383", branch rebuild/pr383-startup-open-warning, head 24e0005e9befe75715db3c133c84b164a2b5d3ee on origin/main 97dcfec1. Old head defb7eaf untouched.
Conflicts: ENVIRONMENT.md (main's + anchors --fix, 22 moved, check 0 wrong); import lines in agent-registry, conformance-sentinel, incident-replay api.py (main moved to install_validation_handler; kept both imports; dropped PR's now-unused RequestValidationError/JSONResponse in agent-registry). Commit 2 identical (=).
Ran: startup-warning test 68 passed; field-core 1558; suites passed: agent-registry 311, attestation-reporter 255, claude-approver 315, compliance-crosswalk 369, conformance-sentinel 263, delegation-authority 257, federation-broker 191, force-gateway 448, incident-replay 97, kill-switch 270, ops-console 457, sealed-ledger 803, spend-governor 291. lifecycle-manager suite not run.
Full range-diff:
1:  2b22bac7 ! 1:  e8266661 field-core and all 14 services: one WARNING per process when a service starts open, naming the setting and never a value (C-804, Don D-21)
    @@ docs/ENVIRONMENT.md: not appear in the scan (none exists today); the scan follow
      | Variable | Component | Default | Accepted values | Security impact | First read |
      |---|---|---|---|---|---|
      | `ANTHROPIC_API_KEY` | compliance-crosswalk, conformance-sentinel, force-gateway | none (unset = judge/suggester/hygiene-judge anthropic mode raises; gateway real upstream answers 502) | any non-empty string; empty counts as unset | credential: never log | compliance_crosswalk/suggestions.py:168 |
    --| `ANTHROPIC_BASE_URL` | field-core, force-gateway | https://api.anthropic.com (trailing / stripped) | URL; plain http to a non-private host only warns, refused if FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1; FORCE_GATEWAY_URL wins in field_core.llm | Wrong value sends the API key to that host. | force_gateway/api.py:205 |
    -+| `ANTHROPIC_BASE_URL` | field-core, force-gateway | https://api.anthropic.com (trailing / stripped) | URL; plain http to a non-private host only warns, refused if FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1; FORCE_GATEWAY_URL wins in field_core.llm | Wrong value sends the API key to that host. | force_gateway/api.py:206 |
    +-| `ANTHROPIC_BASE_URL` | field-core, force-gateway | https://api.anthropic.com (trailing / stripped) | URL; plain http to a non-private host only warns, refused if FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1; FORCE_GATEWAY_URL wins in field_core.llm | Wrong value sends the API key to that host. | force_gateway/api.py:206 |
    ++| `ANTHROPIC_BASE_URL` | field-core, force-gateway | https://api.anthropic.com (trailing / stripped) | URL; plain http to a non-private host only warns, refused if FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1; FORCE_GATEWAY_URL wins in field_core.llm | Wrong value sends the API key to that host. | force_gateway/api.py:207 |
      | `CLAUDE_APPROVER_AGENT_MAP` | claude-approver | none (unset = empty map; approver touches nothing) | inline JSON object, or a path to an existing file if value does not start with '{'; bad JSON empties the whole map, error on /stats | Maps Console agents to FIELD identities; a bad entry is DENIED, bad JSON means no agent is governed. | claude_approver/config.py:30 |
      | `CLAUDE_APPROVER_AGENT_MAP_FILE` | claude-approver | none (falls back to CLAUDE_APPROVER_AGENT_MAP) | path to a JSON file; wins over AGENT_MAP; unreadable file gives empty map with error | Same as AGENT_MAP: wrong path leaves approver with no mapped agents (calls denied). | claude_approver/config.py:31 |
      | `CLAUDE_APPROVER_API_KEY_FILE` | claude-approver | /run/claude-approver/api-key | path; content stripped; missing/unreadable/blank = no key | Holds the approver's API key: file path only, never log contents. | claude_approver/config.py:29 |
    @@ docs/ENVIRONMENT.md: not appear in the scan (none exists today); the scan follow
      | `CROSSWALK_SUGGEST_MODEL` | compliance-crosswalk | claude-sonnet-5 | any string, passed to the API unvalidated (empty string used as is) | none (tunable); wrong id makes suggester calls fail to review-required. | compliance_crosswalk/suggestions.py:166 |
      | `FIELD_ATTEST_SIGNER` | attestation-reporter | none (unset = served packs unsigned) | non-blank string (signer name); must be set together with FIELD_ATTEST_SIGN_KEY; one without the other = status error, packs stay unsigned | Mismatch leaves board packs UNSIGNED; value is the signer identity recorded in the signed pack. | attestation_reporter/signing.py:126 |
      | `FIELD_ATTEST_SIGN_KEY` | attestation-reporter | none (unset = served packs unsigned) | path to unencrypted Ed25519 PEM private key; blank = unset; unreadable/invalid = status error, packs unsigned | credential: path to private key, never log contents. | attestation_reporter/signing.py:127 |
    --| `FIELD_ATTEST_URL` | ops-console | http://127.0.0.1:8013 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Ops-console target for attestation-reporter; wrong URL shows a wrong or unavailable attestation section. | ops_console/api.py:358 |
    -+| `FIELD_ATTEST_URL` | ops-console | http://127.0.0.1:8013 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Ops-console target for attestation-reporter; wrong URL shows a wrong or unavailable attestation section. | ops_console/api.py:359 |
    +-| `FIELD_ATTEST_URL` | ops-console | http://127.0.0.1:8013 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Ops-console target for attestation-reporter; wrong URL shows a wrong or unavailable attestation section. | ops_console/api.py:452 |
    ++| `FIELD_ATTEST_URL` | ops-console | http://127.0.0.1:8013 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Ops-console target for attestation-reporter; wrong URL shows a wrong or unavailable attestation section. | ops_console/api.py:453 |
      | `FIELD_BUILD_SHA` | field-core | unknown | string, stripped; blank = 'unknown' | Label only; a stale or wrong value is reported faithfully and not checked against code. | field_core/buildinfo.py:25 |
    - | `FIELD_CANARY_AGENT_ID` | field-agent | canary-gb10 | any string (CLI --agent-id default) | Identity the canary acts under; wrong id points halts at the wrong agent. | field_agent/canary.py:479 |
    - | `FIELD_CANARY_HEARTBEAT_EVERY` | field-agent | 0.0 (off) | float seconds; blank = default; non-numeric raises ValueError at start; 0 = no heartbeat polls | none (tunable); off means no read-only heartbeat polling. | field_agent/canary.py:483 |
    - | `FIELD_CANARY_HOST` | field-agent | 0.0.0.0 | bind host string (CLI --host default) | Default binds every interface; restrict to loopback or an estate-internal address. | field_agent/canary.py:480 |
    - | `FIELD_CANARY_PORT` | field-agent | 8090 | int; non-integer raises ValueError at start | none (tunable) | field_agent/canary.py:481 |
    - | `FIELD_CANARY_WORK_EVERY` | field-agent | 5.0 | float seconds; blank = default; non-numeric raises ValueError at start | none (tunable) | field_agent/canary.py:482 |
    --| `FIELD_CONSOLE_MAX_STREAMS` | ops-console | 8 | int; non-integer raises ValueError at app start; over the limit new streams get 503 | none (tunable) - caps concurrent SSE streams (resource limit). | ops_console/api.py:364 |
    -+| `FIELD_CONSOLE_MAX_STREAMS` | ops-console | 8 | int; non-integer raises ValueError at app start; over the limit new streams get 503 | none (tunable) - caps concurrent SSE streams (resource limit). | ops_console/api.py:365 |
    + | `FIELD_CANARY_AGENT_ID` | field-agent | canary-gb10 | any string (CLI --agent-id default) | Identity the canary acts under; wrong id points halts at the wrong agent. | field_agent/canary.py:519 |
    + | `FIELD_CANARY_HEARTBEAT_EVERY` | field-agent | 0.0 (off) | float seconds; blank = default; non-numeric raises ValueError at start; 0 = no heartbeat polls | none (tunable); off means no read-only heartbeat polling. | field_agent/canary.py:523 |
    + | `FIELD_CANARY_HOST` | field-agent | 0.0.0.0 | bind host string (CLI --host default) | Default binds every interface; restrict to loopback or an estate-internal address. | field_agent/canary.py:520 |
    + | `FIELD_CANARY_PORT` | field-agent | 8090 | int; non-integer raises ValueError at start | none (tunable) | field_agent/canary.py:521 |
    + | `FIELD_CANARY_WORK_EVERY` | field-agent | 5.0 | float seconds; blank = default; non-numeric raises ValueError at start | none (tunable) | field_agent/canary.py:522 |
    +-| `FIELD_CONSOLE_MAX_STREAMS` | ops-console | 8 | int; non-integer raises ValueError at app start; over the limit new streams get 503 | none (tunable) - caps concurrent SSE streams (resource limit). | ops_console/api.py:458 |
    ++| `FIELD_CONSOLE_MAX_STREAMS` | ops-console | 8 | int; non-integer raises ValueError at app start; over the limit new streams get 503 | none (tunable) - caps concurrent SSE streams (resource limit). | ops_console/api.py:459 |
      | `FIELD_CROSSWALK_EVERY` | compliance-crosswalk | 0 (off) | int seconds via CLI option; non-integer is a CLI usage error; negative treated as 0 | none (tunable); 0 means no scheduled regwatch checks. | compliance_crosswalk/cli.py:351 |
    --| `FIELD_CROSSWALK_URL` | ops-console | http://127.0.0.1:8008 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | ops_console/api.py:350 |
    --| `FIELD_DATA_DIR` | agent-registry, claude-approver, compliance-crosswalk, delegation-authority, federation-broker, force-gateway, kill-switch, lifecycle-manager, sealed-ledger, spend-governor | ./var in most services; '.' in crosswalk staleness store; claude-approver ./var | directory path; blank/unset: claude-approver uses ./var, others use the raw value (blank gives current dir) | Sets where ledger, registry, token and kill-switch SQLite data live; a wrong dir silently starts empty state. | agent_registry/api.py:122 |
    -+| `FIELD_CROSSWALK_URL` | ops-console | http://127.0.0.1:8008 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | ops_console/api.py:351 |
    -+| `FIELD_DATA_DIR` | agent-registry, claude-approver, compliance-crosswalk, delegation-authority, federation-broker, force-gateway, kill-switch, lifecycle-manager, sealed-ledger, spend-governor | ./var in most services; '.' in crosswalk staleness store; claude-approver ./var | directory path; blank/unset: claude-approver uses ./var, others use the raw value (blank gives current dir) | Sets where ledger, registry, token and kill-switch SQLite data live; a wrong dir silently starts empty state. | agent_registry/api.py:123 |
    +-| `FIELD_CROSSWALK_URL` | ops-console | http://127.0.0.1:8008 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | ops_console/api.py:444 |
    +-| `FIELD_DATA_DIR` | agent-registry, claude-approver, compliance-crosswalk, delegation-authority, federation-broker, force-gateway, kill-switch, lifecycle-manager, sealed-ledger, spend-governor | ./var in most services; '.' in crosswalk staleness store; claude-approver ./var | directory path; blank/unset: claude-approver uses ./var, others use the raw value (blank gives current dir) | Sets where ledger, registry, token and kill-switch SQLite data live; a wrong dir silently starts empty state. | agent_registry/api.py:121 |
    ++| `FIELD_CROSSWALK_URL` | ops-console | http://127.0.0.1:8008 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | ops_console/api.py:445 |
    ++| `FIELD_DATA_DIR` | agent-registry, claude-approver, compliance-crosswalk, delegation-authority, federation-broker, force-gateway, kill-switch, lifecycle-manager, sealed-ledger, spend-governor | ./var in most services; '.' in crosswalk staleness store; claude-approver ./var | directory path; blank/unset: claude-approver uses ./var, others use the raw value (blank gives current dir) | Sets where ledger, registry, token and kill-switch SQLite data live; a wrong dir silently starts empty state. | agent_registry/api.py:122 |
      | `FIELD_DELEGATION_URL` | attestation-reporter, compliance-crosswalk, conformance-sentinel, delegation-authority, field-agent, incident-replay, lifecycle-manager, ops-console | http://127.0.0.1:8003 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | field_agent/bootstrap.py:77 |
      | `FIELD_DOA_ROSTER` | delegation-authority | none (unset or blank = DOA mint gate OFF) | path to a YAML roster (grantors list); read per call | Unset = no grantor-authority check on mint; set but unreadable/invalid = mint refused 503 (fail closed). | delegation_authority/doa.py:40 |
    --| `FIELD_EXPORT_ROOT` | sealed-ledger | <ledger dir>/exports (used only when operator auth mode is not off) | directory path; blank = unset; out_dir must resolve inside it, else 422 | Confines ledger export bundles; ignored when operator auth is OFF. | sealed_ledger/api.py:462 |
    -+| `FIELD_EXPORT_ROOT` | sealed-ledger | <ledger dir>/exports (used only when operator auth mode is not off) | directory path; blank = unset; out_dir must resolve inside it, else 422 | Confines ledger export bundles; ignored when operator auth is OFF. | sealed_ledger/api.py:463 |
    +-| `FIELD_EXPORT_ROOT` | sealed-ledger | <ledger dir>/exports (used only when operator auth mode is not off) | directory path; blank = unset; out_dir must resolve inside it, else 422 | Confines ledger export bundles; ignored when operator auth is OFF. | sealed_ledger/api.py:464 |
    ++| `FIELD_EXPORT_ROOT` | sealed-ledger | <ledger dir>/exports (used only when operator auth mode is not off) | directory path; blank = unset; out_dir must resolve inside it, else 422 | Confines ledger export bundles; ignored when operator auth is OFF. | sealed_ledger/api.py:465 |
      | `FIELD_FEDERATION_URL` | federation-broker, field-agent, ops-console | http://127.0.0.1:8010 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | field_agent/federation.py:60 |
      | `FIELD_GATEWAY_URL` | force-gateway, ops-console | http://127.0.0.1:8009 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | force_gateway/cli.py:24 |
      | `FIELD_GOVERNOR_URL` | attestation-reporter, claude-approver, compliance-crosswalk, conformance-sentinel, field-agent, force-gateway, lifecycle-manager, ops-console, spend-governor | http://127.0.0.1:8006 (force-gateway serve: unset = no governor client, usage not metered) | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | field_agent/usage.py:74 |
      | `FIELD_JUDGE_CONFIDENCE_FLOOR` | conformance-sentinel | 0.8 | float clamped to [0,1]; empty or non-numeric falls back to 0.8 | Lower floor lets less confident semantic-judge verdicts act; higher defers more. | conformance_sentinel/judge.py:201 |
      | `FIELD_JUDGE_MODEL` | conformance-sentinel | claude-sonnet-5 | any string passed to the API unvalidated | none (tunable); wrong id makes judge calls fail. | conformance_sentinel/judge.py:133 |
    - | `FIELD_KILLSWITCH_URL` | claude-approver, field-agent, kill-switch, lifecycle-manager, ops-console | http://127.0.0.1:8005 (canary x3-check: required, exits 2 if unset) | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Wrong URL breaks heartbeats and halts for agents using it. | field_agent/canary.py:492 |
    --| `FIELD_KILL_ENDPOINT_ALLOWLIST` | kill-switch | none (unset/blank = outbound kill signal skipped, reason allowlist_unset) | comma-separated exact hostnames (no port); host must match exactly; manifest host is lowercased so list lowercase | Unset disarms the outbound halt signal; a broad list lets the service POST to those hosts. | kill_switch/api.py:269 |
    --| `FIELD_LEDGER_ANCHOR_KEY` | sealed-ledger | none (unset = rotation refused, 503 NoAnchorKey) | path to unencrypted Ed25519 PEM private key; read per call; any failure = 503 | credential: path to private key, never log contents. | sealed_ledger/api.py:52 |
    --| `FIELD_LEDGER_ARCHIVE_DIR` | sealed-ledger | <FIELD_DATA_DIR>/ledger-archive | directory path; blank = unset; archive refused if inside live ledger dir, or outside FIELD_DATA_DIR unless allow_external | Where rotated segments are archived; a wrong path archives outside the intended store. | sealed_ledger/api.py:53 |
    -+| `FIELD_KILL_ENDPOINT_ALLOWLIST` | kill-switch | none (unset/blank = outbound kill signal skipped, reason allowlist_unset) | comma-separated exact hostnames (no port); host must match exactly; manifest host is lowercased so list lowercase | Unset disarms the outbound halt signal; a broad list lets the service POST to those hosts. | kill_switch/api.py:270 |
    -+| `FIELD_LEDGER_ANCHOR_KEY` | sealed-ledger | none (unset = rotation refused, 503 NoAnchorKey) | path to unencrypted Ed25519 PEM private key; read per call; any failure = 503 | credential: path to private key, never log contents. | sealed_ledger/api.py:53 |
    -+| `FIELD_LEDGER_ARCHIVE_DIR` | sealed-ledger | <FIELD_DATA_DIR>/ledger-archive | directory path; blank = unset; archive refused if inside live ledger dir, or outside FIELD_DATA_DIR unless allow_external | Where rotated segments are archived; a wrong path archives outside the intended store. | sealed_ledger/api.py:54 |
    - | `FIELD_LEDGER_CALLER_ID` | field-core | none (unset = ledger appends are unsigned by this caller) | string, stripped; must be set together with FIELD_LEDGER_CALLER_KEY, else one warning and unsigned | Mismatch silently leaves this caller's appends unsigned; ledger needs a matching <id>.pub.pem. | field_core/clients.py:67 |
    - | `FIELD_LEDGER_CALLER_KEY` | field-core | none (unset = ledger appends are unsigned by this caller) | path to Ed25519 PEM private key; unreadable or unusable = one warning and appends unsigned | credential: path to private key, never log contents. | field_core/clients.py:68 |
    + | `FIELD_KILLSWITCH_URL` | claude-approver, field-agent, kill-switch, lifecycle-manager, ops-console | http://127.0.0.1:8005 (canary x3-check: required, exits 2 if unset) | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Wrong URL breaks heartbeats and halts for agents using it. | field_agent/canary.py:532 |
    +-| `FIELD_KILL_ENDPOINT_ALLOWLIST` | kill-switch | none (unset/blank = outbound kill signal skipped, reason allowlist_unset) | comma-separated exact hostnames (no port); host must match exactly; manifest host is lowercased so list lowercase | Unset disarms the outbound halt signal; a broad list lets the service POST to those hosts. | kill_switch/api.py:294 |
    +-| `FIELD_LEDGER_ANCHOR_KEY` | sealed-ledger | none (unset = rotation refused, 503 NoAnchorKey) | path to unencrypted Ed25519 PEM private key; read per call; any failure = 503 | credential: path to private key, never log contents. | sealed_ledger/api.py:53 |
    +-| `FIELD_LEDGER_ARCHIVE_DIR` | sealed-ledger | <FIELD_DATA_DIR>/ledger-archive | directory path; blank = unset; archive refused if inside live ledger dir, or outside FIELD_DATA_DIR unless allow_external | Where rotated segments are archived; a wrong path archives outside the intended store. | sealed_ledger/api.py:54 |
    ++| `FIELD_KILL_ENDPOINT_ALLOWLIST` | kill-switch | none (unset/blank = outbound kill signal skipped, reason allowlist_unset) | comma-separated exact hostnames (no port); host must match exactly; manifest host is lowercased so list lowercase | Unset disarms the outbound halt signal; a broad list lets the service POST to those hosts. | kill_switch/api.py:295 |
    ++| `FIELD_LEDGER_ANCHOR_KEY` | sealed-ledger | none (unset = rotation refused, 503 NoAnchorKey) | path to unencrypted Ed25519 PEM private key; read per call; any failure = 503 | credential: path to private key, never log contents. | sealed_ledger/api.py:54 |
    ++| `FIELD_LEDGER_ARCHIVE_DIR` | sealed-ledger | <FIELD_DATA_DIR>/ledger-archive | directory path; blank = unset; archive refused if inside live ledger dir, or outside FIELD_DATA_DIR unless allow_external | Where rotated segments are archived; a wrong path archives outside the intended store. | sealed_ledger/api.py:55 |
    + | `FIELD_LEDGER_CALLER_ID` | field-core | none (unset = ledger appends are unsigned by this caller) | string, stripped; must be set together with FIELD_LEDGER_CALLER_KEY, else one warning and unsigned | Mismatch silently leaves this caller's appends unsigned; ledger needs a matching <id>.pub.pem. | field_core/clients.py:68 |
    + | `FIELD_LEDGER_CALLER_KEY` | field-core | none (unset = ledger appends are unsigned by this caller) | path to Ed25519 PEM private key; unreadable or unusable = one warning and appends unsigned | credential: path to private key, never log contents. | field_core/clients.py:69 |
      | `FIELD_LEDGER_CALLER_KEYRING` | sealed-ledger | none (unset/blank = no keyring) | directory of <caller_id>.pub.pem files; missing dir = every caller unknown | With no keyring any signed caller claim is refused 403. | sealed_ledger/store.py:134 |
     @@ docs/ENVIRONMENT.md: not appear in the scan (none exists today); the scan follows `os.environ`, its a
      | `FIELD_LEDGER_RETENTION_DAYS` | sealed-ledger | none (unset/blank = no estate policy) | integer >= 1; non-integer or < 1 is ignored and reported as a problem | Unset means no retention policy is checked; check reports a violation when a manifest exceeds it. | sealed_ledger/retention.py:23 |
      | `FIELD_LEDGER_SIGN_KEY` | sealed-ledger | none (unset = unsigned sha-256 chain) | path to Ed25519 PEM private key; blank = unset; unreadable/malformed = signing 'error' on /health, behaviour follows REQUIRE_SIGNING | credential: path to private key, never log contents. | sealed_ledger/store.py:123 |
    - | `FIELD_LEDGER_URL` | agent-registry, attestation-reporter, compliance-crosswalk, conformance-sentinel, field-agent, field-core, force-gateway, incident-replay, lifecycle-manager, ops-console, sealed-ledger, spend-governor | http://127.0.0.1:8002; none for registry, force-gateway, spend-governor serve (unset = no ledger client); sealed-ledger CLI errors unless --offline | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Unset means those services do not write audit events to the ledger. | field_agent/canary.py:492 |
    --| `FIELD_LIFECYCLE_EVERY` | lifecycle-manager | 0 (off) | API: digits only else 0; CLI: int, non-integer is a usage error; negative = 0 | 0 means no scheduled sweep; scheduler never arms auto-kill. | lifecycle_manager/api.py:68 |
    --| `FIELD_LIFECYCLE_ROSTER` | lifecycle-manager | none (unset = POST /sweep without roster_csv answers 503) | path to owners roster CSV; missing file or roster with no owners = 503 | Roster defines owners; an empty or missing one refuses the sweep, and auto-kill uses only this configured roster. | lifecycle_manager/api.py:67 |
    --| `FIELD_LIFECYCLE_URL` | ops-console | http://127.0.0.1:8012 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | ops_console/api.py:356 |
    -+| `FIELD_LIFECYCLE_EVERY` | lifecycle-manager | 0 (off) | API: digits only else 0; CLI: int, non-integer is a usage error; negative = 0 | 0 means no scheduled sweep; scheduler never arms auto-kill. | lifecycle_manager/api.py:69 |
    -+| `FIELD_LIFECYCLE_ROSTER` | lifecycle-manager | none (unset = POST /sweep without roster_csv answers 503) | path to owners roster CSV; missing file or roster with no owners = 503 | Roster defines owners; an empty or missing one refuses the sweep, and auto-kill uses only this configured roster. | lifecycle_manager/api.py:68 |
    -+| `FIELD_LIFECYCLE_URL` | ops-console | http://127.0.0.1:8012 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | ops_console/api.py:357 |
    - | `FIELD_MANIFEST_DIR` | agent-registry, conformance-sentinel, field-core, ops-console | . (current dir); ops-console: none (unset = manifest viewer refuses 403) | directory path; manifest_ref resolves relative to it | Wrong dir makes manifests unresolvable (agents blocked I.manifest); in ops-console must contain viewed manifests. | field_core/clients.py:452 |
    + | `FIELD_LEDGER_URL` | agent-registry, attestation-reporter, compliance-crosswalk, conformance-sentinel, field-agent, field-core, force-gateway, incident-replay, lifecycle-manager, ops-console, sealed-ledger, spend-governor | http://127.0.0.1:8002; none for registry, force-gateway, spend-governor serve (unset = no ledger client); sealed-ledger CLI errors unless --offline | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Unset means those services do not write audit events to the ledger. | field_agent/canary.py:532 |
    +-| `FIELD_LIFECYCLE_EVERY` | lifecycle-manager | 0 (off) | API: digits only else 0; CLI: int, non-integer is a usage error; negative = 0 | 0 means no scheduled sweep; scheduler never arms auto-kill. | lifecycle_manager/api.py:70 |
    +-| `FIELD_LIFECYCLE_ROSTER` | lifecycle-manager | none (unset = POST /sweep without roster_csv answers 503) | path to owners roster CSV; missing file or roster with no owners = 503 | Roster defines owners; an empty or missing one refuses the sweep, and auto-kill uses only this configured roster. | lifecycle_manager/api.py:69 |
    +-| `FIELD_LIFECYCLE_URL` | ops-console | http://127.0.0.1:8012 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | ops_console/api.py:450 |
    ++| `FIELD_LIFECYCLE_EVERY` | lifecycle-manager | 0 (off) | API: digits only else 0; CLI: int, non-integer is a usage error; negative = 0 | 0 means no scheduled sweep; scheduler never arms auto-kill. | lifecycle_manager/api.py:71 |
    ++| `FIELD_LIFECYCLE_ROSTER` | lifecycle-manager | none (unset = POST /sweep without roster_csv answers 503) | path to owners roster CSV; missing file or roster with no owners = 503 | Roster defines owners; an empty or missing one refuses the sweep, and auto-kill uses only this configured roster. | lifecycle_manager/api.py:70 |
    ++| `FIELD_LIFECYCLE_URL` | ops-console | http://127.0.0.1:8012 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | ops_console/api.py:451 |
    + | `FIELD_MANIFEST_DIR` | agent-registry, conformance-sentinel, field-core, ops-console | . (current dir); ops-console: none (unset = manifest viewer refuses 403) | directory path; manifest_ref resolves relative to it | Wrong dir makes manifests unresolvable (agents blocked I.manifest); in ops-console must contain viewed manifests. | field_core/clients.py:466 |
      | `FIELD_NTFY_BASE_URL` | field-core | https://ntfy.sh | https URL, or http only to loopback; no userinfo/query/fragment; invalid = alerts not sent (base_url_invalid) | Alerts go to this server; a wrong value misroutes them. | field_core/alerts.py:79 |
      | `FIELD_NTFY_TOKEN` | field-core | none (unset = no access token) | 8-256 chars of [A-Za-z0-9._~+/=-]; invalid = alerts not sent (token_invalid) | credential: never log | field_core/alerts.py:81 |
     @@ docs/ENVIRONMENT.md: not appear in the scan (none exists today); the scan follows `os.environ`, its a
      | `FIELD_WITNESS_ESTATE_WATCHED` | lifecycle-manager | fly | any string, stripped; blank = fly | Names the remote estate whose anchor.remote the sweep checks; wrong name reports a stale or absent witness. | lifecycle_manager/engine.py:156 |
      | `FIELD_WITNESS_EVERY` | lifecycle-manager | none (unset/blank = no witness expected, no finding) | positive integer seconds; any other non-blank value = misconfigured finding | Unset means a stale or missing remote witness is never flagged. | lifecycle_manager/engine.py:155 |
      | `FIELD_WITNESS_FLY_SECRET_FILE` | sealed-ledger | none (unset = direction 2 not live, nothing sent) | path to a file holding the remote's secret; stripped; unreadable or empty = not sent | credential: path only, never log contents. | sealed_ledger/witness.py:60 |
    --| `FORCE_GATEWAY_BYPASS_COOLDOWN` | force-gateway | 10 | int requests; non-integer raises ValueError at app start | Number of requests forwarded uninstrumented (no FORCE injection or telemetry) after a fault or latency breach; higher = longer gap. | force_gateway/api.py:804 |
    --| `FORCE_GATEWAY_ENFORCE` | force-gateway | off (observer only) | 1/true/yes/on enforces, 0/false/no/off or unset/blank = off (any case, whitespace ignored); anything else refuses to start | Off means no identity or authority check at the LLM egress. A typo stops the gateway (C-180). | force_gateway/api.py:270 |
    --| `FORCE_GATEWAY_LATENCY_BUDGET_MS` | force-gateway | 250 | float ms; non-numeric raises ValueError at app start | Instrumentation over this budget drops the gateway to bypass; too low causes frequent uninstrumented bypass. | force_gateway/api.py:801 |
    --| `FORCE_GATEWAY_MOCK` | force-gateway | off (real upstream) | exactly '1' = mock upstream; any other value = real upstream | Mock serves canned responses, not the model; never set in production. | force_gateway/api.py:230 |
    -+| `FORCE_GATEWAY_BYPASS_COOLDOWN` | force-gateway | 10 | int requests; non-integer raises ValueError at app start | Number of requests forwarded uninstrumented (no FORCE injection or telemetry) after a fault or latency breach; higher = longer gap. | force_gateway/api.py:815 |
    -+| `FORCE_GATEWAY_ENFORCE` | force-gateway | off (observer only) | 1/true/yes/on enforces, 0/false/no/off or unset/blank = off (any case, whitespace ignored); anything else refuses to start | Off means no identity or authority check at the LLM egress. A typo stops the gateway (C-180). | force_gateway/api.py:271 |
    -+| `FORCE_GATEWAY_LATENCY_BUDGET_MS` | force-gateway | 250 | float ms; non-numeric raises ValueError at app start | Instrumentation over this budget drops the gateway to bypass; too low causes frequent uninstrumented bypass. | force_gateway/api.py:812 |
    -+| `FORCE_GATEWAY_MOCK` | force-gateway | off (real upstream) | exactly '1' = mock upstream; any other value = real upstream | Mock serves canned responses, not the model; never set in production. | force_gateway/api.py:231 |
    - | `FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM` | field-core, force-gateway | off | 1/true/yes/on = refuse API key over plain http to a non-internal host; 0/false/no/off or unset/blank = off (warn only); anything else refuses to start in force-gateway and is read as ON by field-core (a library cannot refuse to start) | Off only warns, so the key goes unencrypted to a plain-http upstream. A typo can no longer leave it off silently (C-180). | field_core/llm.py:119 |
    +-| `FORCE_GATEWAY_BYPASS_COOLDOWN` | force-gateway | 10 | int requests; non-integer raises ValueError at app start | Number of requests forwarded uninstrumented (no FORCE injection or telemetry) after a fault or latency breach; higher = longer gap. | force_gateway/api.py:806 |
    +-| `FORCE_GATEWAY_ENFORCE` | force-gateway | off (observer only) | 1/true/yes/on enforces, 0/false/no/off or unset/blank = off (any case, whitespace ignored); anything else refuses to start | Off means no identity or authority check at the LLM egress. A typo stops the gateway (C-180). | force_gateway/api.py:271 |
    +-| `FORCE_GATEWAY_LATENCY_BUDGET_MS` | force-gateway | 250 | float ms; non-numeric raises ValueError at app start | Instrumentation over this budget drops the gateway to bypass; too low causes frequent uninstrumented bypass. | force_gateway/api.py:803 |
    +-| `FORCE_GATEWAY_MOCK` | force-gateway | off (real upstream) | exactly '1' = mock upstream; any other value = real upstream | Mock serves canned responses, not the model; never set in production. | force_gateway/api.py:236 |
    ++| `FORCE_GATEWAY_BYPASS_COOLDOWN` | force-gateway | 10 | int requests; non-integer raises ValueError at app start | Number of requests forwarded uninstrumented (no FORCE injection or telemetry) after a fault or latency breach; higher = longer gap. | force_gateway/api.py:817 |
    ++| `FORCE_GATEWAY_ENFORCE` | force-gateway | off (observer only) | 1/true/yes/on enforces, 0/false/no/off or unset/blank = off (any case, whitespace ignored); anything else refuses to start | Off means no identity or authority check at the LLM egress. A typo stops the gateway (C-180). | force_gateway/api.py:272 |
    ++| `FORCE_GATEWAY_LATENCY_BUDGET_MS` | force-gateway | 250 | float ms; non-numeric raises ValueError at app start | Instrumentation over this budget drops the gateway to bypass; too low causes frequent uninstrumented bypass. | force_gateway/api.py:814 |
    ++| `FORCE_GATEWAY_MOCK` | force-gateway | off (real upstream) | exactly '1' = mock upstream; any other value = real upstream | Mock serves canned responses, not the model; never set in production. | force_gateway/api.py:237 |
    + | `FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM` | field-core, force-gateway | off | 1/true/yes/on = refuse API key over plain http to a non-internal host; 0/false/no/off or unset/blank = off (warn only); anything else refuses to start in force-gateway and is read as ON by field-core (a library cannot refuse to start) | Off only warns, so the key goes unencrypted to a plain-http upstream. A typo can no longer leave it off silently (C-180). | field_core/llm.py:117 |
      | `FORCE_GATEWAY_SAMPLE_EVERY` | force-gateway | 10 | int; 0 or negative = never sample; non-integer or blank falls back to 10 | none (tunable); 0 disables hygiene judging coverage. | force_gateway/hygiene_judge.py:176 |
    --| `FORCE_GATEWAY_SENTINEL_TIMEOUT` | force-gateway | 30.0 | float seconds > 0; non-numeric or <= 0 falls back to 30.0 | Too short makes enforce-mode checks time out, which refuse 503; too long delays calls. | force_gateway/api.py:273 |
    --| `FORCE_GATEWAY_TOOL_CHECK` | force-gateway | off | 1/true/yes/on = on, 0/false/no/off or unset/blank = off (any case, whitespace ignored); anything else refuses to start; meaningful only with FORCE_GATEWAY_ENFORCE on | Off means tool_use blocks in responses are not checked at the egress. A typo stops the gateway (C-180). | force_gateway/api.py:271 |
    -+| `FORCE_GATEWAY_SENTINEL_TIMEOUT` | force-gateway | 30.0 | float seconds > 0; non-numeric or <= 0 falls back to 30.0 | Too short makes enforce-mode checks time out, which refuse 503; too long delays calls. | force_gateway/api.py:274 |
    -+| `FORCE_GATEWAY_TOOL_CHECK` | force-gateway | off | 1/true/yes/on = on, 0/false/no/off or unset/blank = off (any case, whitespace ignored); anything else refuses to start; meaningful only with FORCE_GATEWAY_ENFORCE on | Off means tool_use blocks in responses are not checked at the egress. A typo stops the gateway (C-180). | force_gateway/api.py:272 |
    - | `FORCE_GATEWAY_URL` | field-core | none (unset = Messages calls go to ANTHROPIC_BASE_URL, else https://api.anthropic.com) | URL, stripped, trailing / removed; blank = unset; cleartext only to https or estate-internal host, else error | Unset means platform LLM calls bypass the FORCE gateway; wrong value sends key and platform headers there. | field_core/llm.py:57 |
    --| `FORCE_HYGIENE_BAND` | force-gateway | 0.15 | float; non-numeric raises ValueError at app start | none (tunable) - drift alert band. | force_gateway/api.py:796 |
    --| `FORCE_HYGIENE_BASELINE_WINDOWS` | force-gateway | 2 | int; non-integer raises ValueError at app start | none (tunable) | force_gateway/api.py:797 |
    -+| `FORCE_HYGIENE_BAND` | force-gateway | 0.15 | float; non-numeric raises ValueError at app start | none (tunable) - drift alert band. | force_gateway/api.py:807 |
    -+| `FORCE_HYGIENE_BASELINE_WINDOWS` | force-gateway | 2 | int; non-integer raises ValueError at app start | none (tunable) | force_gateway/api.py:808 |
    +-| `FORCE_GATEWAY_SENTINEL_TIMEOUT` | force-gateway | 30.0 | float seconds > 0; non-numeric or <= 0 falls back to 30.0 | Too short makes enforce-mode checks time out, which refuse 503; too long delays calls. | force_gateway/api.py:274 |
    +-| `FORCE_GATEWAY_TOOL_CHECK` | force-gateway | off | 1/true/yes/on = on, 0/false/no/off or unset/blank = off (any case, whitespace ignored); anything else refuses to start; meaningful only with FORCE_GATEWAY_ENFORCE on | Off means tool_use blocks in responses are not checked at the egress. A typo stops the gateway (C-180). | force_gateway/api.py:272 |
    ++| `FORCE_GATEWAY_SENTINEL_TIMEOUT` | force-gateway | 30.0 | float seconds > 0; non-numeric or <= 0 falls back to 30.0 | Too short makes enforce-mode checks time out, which refuse 503; too long delays calls. | force_gateway/api.py:275 |
    ++| `FORCE_GATEWAY_TOOL_CHECK` | force-gateway | off | 1/true/yes/on = on, 0/false/no/off or unset/blank = off (any case, whitespace ignored); anything else refuses to start; meaningful only with FORCE_GATEWAY_ENFORCE on | Off means tool_use blocks in responses are not checked at the egress. A typo stops the gateway (C-180). | force_gateway/api.py:273 |
    + | `FORCE_GATEWAY_URL` | field-core | none (unset = Messages calls go to ANTHROPIC_BASE_URL, else https://api.anthropic.com) | URL, stripped, trailing / removed; blank = unset; cleartext only to https or estate-internal host, else error | Unset means platform LLM calls bypass the FORCE gateway; wrong value sends key and platform headers there. | field_core/llm.py:55 |
    +-| `FORCE_HYGIENE_BAND` | force-gateway | 0.15 | float; non-numeric raises ValueError at app start | none (tunable) - drift alert band. | force_gateway/api.py:798 |
    +-| `FORCE_HYGIENE_BASELINE_WINDOWS` | force-gateway | 2 | int; non-integer raises ValueError at app start | none (tunable) | force_gateway/api.py:799 |
    ++| `FORCE_HYGIENE_BAND` | force-gateway | 0.15 | float; non-numeric raises ValueError at app start | none (tunable) - drift alert band. | force_gateway/api.py:809 |
    ++| `FORCE_HYGIENE_BASELINE_WINDOWS` | force-gateway | 2 | int; non-integer raises ValueError at app start | none (tunable) | force_gateway/api.py:810 |
      | `FORCE_HYGIENE_JUDGE` | force-gateway | off (none) | off \| mock \| anthropic (strip, case-insensitive); unrecognised = OFF | A typo leaves the hygiene judge off; 'anthropic' adds LLM calls. | force_gateway/hygiene_judge.py:165 |
      | `FORCE_HYGIENE_JUDGE_MODEL` | force-gateway | claude-haiku-4-5-20251001 | any string passed to the API unvalidated | none (tunable); wrong id makes judge calls fail. | force_gateway/hygiene_judge.py:115 |
    --| `FORCE_HYGIENE_WINDOW` | force-gateway | 5 | int; non-integer raises ValueError at app start | none (tunable) | force_gateway/api.py:795 |
    -+| `FORCE_HYGIENE_WINDOW` | force-gateway | 5 | int; non-integer raises ValueError at app start | none (tunable) | force_gateway/api.py:806 |
    +-| `FORCE_HYGIENE_WINDOW` | force-gateway | 5 | int; non-integer raises ValueError at app start | none (tunable) | force_gateway/api.py:797 |
    ++| `FORCE_HYGIENE_WINDOW` | force-gateway | 5 | int; non-integer raises ValueError at app start | none (tunable) | force_gateway/api.py:808 |
      | `FORCE_TELEMETRY_RETAIN` | force-gateway | 10000 | int clamped to >= 1; non-integer or blank falls back to 10000 | none (tunable) - telemetry rows kept. | force_gateway/store.py:71 |
    --| `FORCE_TELEMETRY_WINDOW` | force-gateway | 50 | int clamped to >= 1; non-integer or blank falls back to 50 | none (tunable) - last_N window size. | force_gateway/api.py:243 |
    -+| `FORCE_TELEMETRY_WINDOW` | force-gateway | 50 | int clamped to >= 1; non-integer or blank falls back to 50 | none (tunable) - last_N window size. | force_gateway/api.py:244 |
    +-| `FORCE_TELEMETRY_WINDOW` | force-gateway | 50 | int clamped to >= 1; non-integer or blank falls back to 50 | none (tunable) - last_N window size. | force_gateway/api.py:244 |
    ++| `FORCE_TELEMETRY_WINDOW` | force-gateway | 50 | int clamped to >= 1; non-integer or blank falls back to 50 | none (tunable) - last_N window size. | force_gateway/api.py:245 |
     
      ## packages/field-core/src/field_core/startup.py (new) ##
     @@
    @@ services/agent-registry/src/agent_registry/api.py: from typing import Any
      
      from field_core import operator_auth, operator_health
     +from field_core.startup import warn_open
    - from fastapi.exceptions import RequestValidationError
    - from fastapi.responses import JSONResponse
      
    + from field_core.authn import install as install_authn
    + from field_core.buildinfo import build_sha
     @@ services/agent-registry/src/agent_registry/api.py: def create_app(store: RegistryStore | None = None, ledger=None) -> FastAPI:
              except ScanInputError as exc:  # malformed or > 1 MiB: never an empty report
                  raise HTTPException(422, str(exc))
    @@ services/compliance-crosswalk/src/compliance_crosswalk/api.py: def create_app(st
      
     
      ## services/conformance-sentinel/src/conformance_sentinel/api.py ##
    -@@ services/conformance-sentinel/src/conformance_sentinel/api.py: from __future__ import annotations
    - from fastapi import FastAPI
    +@@ services/conformance-sentinel/src/conformance_sentinel/api.py: from fastapi import FastAPI
      
      from field_core.authn import install as install_authn
    + from field_core.http_errors import install_validation_handler
     +from field_core.startup import warn_open
      from field_core.buildinfo import build_sha
      
    @@ services/force-gateway/src/force_gateway/api.py: from fastapi import FastAPI, He
      from field_core import posture_flag
     +from field_core.startup import warn_open
      from field_core.authn import auth_headers, install as install_authn, shared_secret
    + from field_core.http_errors import install_validation_handler
      from field_core.buildinfo import build_sha
    - from field_core.llm import AGENT_ID_HEADER, EGRESS_ACTION, TOKEN_HEADER
     @@ services/force-gateway/src/force_gateway/api.py: def resolve_enforce() -> bool:
          return _posture_flag(ENFORCE_ENV)
      
    @@ services/force-gateway/src/force_gateway/api.py: def create_app(upstream: Upstre
          return app
     
      ## services/incident-replay/src/incident_replay/api.py ##
    -@@ services/incident-replay/src/incident_replay/api.py: from __future__ import annotations
    - from fastapi import FastAPI
    +@@ services/incident-replay/src/incident_replay/api.py: from fastapi import FastAPI
      
      from field_core.authn import install as install_authn
    + from field_core.http_errors import install_validation_handler
     +from field_core.startup import warn_open
      from field_core.buildinfo import build_sha
      from fastapi.responses import PlainTextResponse
    @@ services/incident-replay/src/incident_replay/api.py: def create_app(engine: Repl
          return app
     
      ## services/kill-switch/src/kill_switch/api.py ##
    -@@ services/kill-switch/src/kill_switch/api.py: from urllib.parse import quote, urlsplit
    +@@ services/kill-switch/src/kill_switch/api.py: from urllib.parse import quote, unquote, urlsplit
      from fastapi import Depends, FastAPI, HTTPException, Request
      
      from field_core import operator_auth, operator_health
     +from field_core.startup import warn_open
      
      from field_core.authn import install as install_authn
    - from field_core.buildinfo import build_sha
    + from field_core.http_errors import install_validation_handler
     @@ services/kill-switch/src/kill_switch/api.py: def create_app(
                  raise HTTPException(500, report.model_dump(mode="json"))
              return report
    @@ services/lifecycle-manager/src/lifecycle_manager/api.py: from fastapi import Dep
     +from field_core.startup import warn_open
      from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
      
    - from field_core.authn import auth_headers
    + from field_core.http_errors import install_validation_handler
     @@ services/lifecycle-manager/src/lifecycle_manager/api.py: def create_app(
                  data = {**data, "last_tick": tick}
              return data
    @@ services/lifecycle-manager/src/lifecycle_manager/api.py: def create_app(
     
      ## services/ops-console/src/ops_console/api.py ##
     @@ services/ops-console/src/ops_console/api.py: from fastapi.responses import HTMLResponse, Response, StreamingResponse
    - from pydantic import BaseModel, ConfigDict, Field
    + from pydantic import BaseModel, ConfigDict, Field, field_validator
      
      from field_core import operator_auth, operator_health
     +from field_core.startup import warn_open
      from field_core.authn import HEADER as AUTH_HEADER, install as install_authn, shared_secret
    + from field_core.http_errors import install_validation_handler
      from field_core.buildinfo import build_sha
    - from field_core.clients import (
     @@ services/ops-console/src/ops_console/api.py: def create_app(
              is real and lands on the ledger like any other check."""
              return _proxy(app.state.sentinel, "/check", req.model_dump())
    @@ services/sealed-ledger/src/sealed_ledger/api.py: from cryptography.hazmat.primit
     +from field_core.startup import warn_open
      
      from field_core.authn import install as install_authn
    - from field_core.buildinfo import build_sha
    + from field_core.http_errors import install_validation_handler
     @@ services/sealed-ledger/src/sealed_ledger/api.py: def create_app(store: LedgerStore | None = None, registry: Any = _UNSET,
              status ``ok``."""
              return retention_check(_store(), _registry())
2:  defb7eaf = 2:  24e0005e startup warning: pin the name guard, state that log-only is not open, and stop echoing a bad FIELD_OPERATOR_REQUIRE value (C-888, C-43)
