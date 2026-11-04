builder-1: B-REBUILD-PR326 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/547 "rebuild of #326", branch rebuild/pr326-upstream-error-body, head a9066499dc5403e7f244d264b572338871885151, on origin/main 97dcfec1. Old head da33a9a1 untouched.
MORE THAN CONFLICT RESOLUTION: PR 326's first commit 203810fb (C-503) is already on main as 63e91b21, so it was dropped; only da33a9a1 (C-642) is carried. Rebuilt diff 9 files +256/-33. Coordinator: confirm the GX10 16/16 on the old head still covers this smaller diff (I do not know).
Conflicts: docs/ENVIRONMENT.md (main's file + tools/environment_anchors.py --fix, 2 anchors moved, --check 0 wrong); liveness.py (main independently wrote 'heartbeat returned {status}'; kept PR's upstream_error helper, same string for an int status).
Ran: field-core 1549 passed 1 skipped; conformance-sentinel 262 passed; field-agent 221 passed 1 failed (test_canary_agent.py::test_the_process_never_exits_on_a_halt, also fails on unmodified origin/main here); tools environment tests 98 passed.
Full git range-diff output:
1:  203810fb < -:  -------- field-core, field-agent, sentinel: an upstream reply's body is never part of an error message; one helper returns the status only (C-503, design note C-490 findings 1 and 3)
2:  da33a9a1 ! 1:  a9066499 field-agent: the SDK's own errors carry no upstream body; sentinel /check behaviour test; helper properties, status formatting and exception chain pinned (C-642, reviewer C-584 F-C584-1/-2/-4/-5; C-685 F-C685-1/-2)
    @@ docs/ENVIRONMENT.md
     @@ docs/ENVIRONMENT.md: not appear in the scan (none exists today); the scan follows `os.environ`, its a
      | `FIELD_DELEGATION_URL` | attestation-reporter, compliance-crosswalk, conformance-sentinel, delegation-authority, field-agent, incident-replay, lifecycle-manager, ops-console | http://127.0.0.1:8003 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | field_agent/bootstrap.py:77 |
      | `FIELD_DOA_ROSTER` | delegation-authority | none (unset or blank = DOA mint gate OFF) | path to a YAML roster (grantors list); read per call | Unset = no grantor-authority check on mint; set but unreadable/invalid = mint refused 503 (fail closed). | delegation_authority/doa.py:40 |
    - | `FIELD_EXPORT_ROOT` | sealed-ledger | <ledger dir>/exports (used only when operator auth mode is not off) | directory path; blank = unset; out_dir must resolve inside it, else 422 | Confines ledger export bundles; ignored when operator auth is OFF. | sealed_ledger/api.py:462 |
    + | `FIELD_EXPORT_ROOT` | sealed-ledger | <ledger dir>/exports (used only when operator auth mode is not off) | directory path; blank = unset; out_dir must resolve inside it, else 422 | Confines ledger export bundles; ignored when operator auth is OFF. | sealed_ledger/api.py:464 |
     -| `FIELD_FEDERATION_URL` | federation-broker, field-agent, ops-console | http://127.0.0.1:8010 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | field_agent/federation.py:60 |
     +| `FIELD_FEDERATION_URL` | federation-broker, field-agent, ops-console | http://127.0.0.1:8010 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | field_agent/federation.py:61 |
      | `FIELD_GATEWAY_URL` | force-gateway, ops-console | http://127.0.0.1:8009 | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | force_gateway/cli.py:24 |
    @@ docs/ENVIRONMENT.md: not appear in the scan (none exists today); the scan follow
     +| `FIELD_GOVERNOR_URL` | attestation-reporter, claude-approver, compliance-crosswalk, conformance-sentinel, field-agent, force-gateway, lifecycle-manager, ops-console, spend-governor | http://127.0.0.1:8006 (force-gateway serve: unset = no governor client, usage not metered) | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Points this client at that service; a wrong or attacker URL redirects governed calls (and the shared secret header). | field_agent/usage.py:75 |
      | `FIELD_JUDGE_CONFIDENCE_FLOOR` | conformance-sentinel | 0.8 | float clamped to [0,1]; empty or non-numeric falls back to 0.8 | Lower floor lets less confident semantic-judge verdicts act; higher defers more. | conformance_sentinel/judge.py:201 |
      | `FIELD_JUDGE_MODEL` | conformance-sentinel | claude-sonnet-5 | any string passed to the API unvalidated | none (tunable); wrong id makes judge calls fail. | conformance_sentinel/judge.py:133 |
    - | `FIELD_KILLSWITCH_URL` | claude-approver, field-agent, kill-switch, lifecycle-manager, ops-console | http://127.0.0.1:8005 (canary x3-check: required, exits 2 if unset) | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Wrong URL breaks heartbeats and halts for agents using it. | field_agent/canary.py:492 |
    + | `FIELD_KILLSWITCH_URL` | claude-approver, field-agent, kill-switch, lifecycle-manager, ops-console | http://127.0.0.1:8005 (canary x3-check: required, exits 2 if unset) | http(s) base URL; trailing / stripped; not validated at read; unreachable host just fails calls | Wrong URL breaks heartbeats and halts for agents using it. | field_agent/canary.py:532 |
     
      ## packages/field-agent/src/field_agent/federation.py ##
     @@ packages/field-agent/src/field_agent/federation.py: from __future__ import annotations
    @@ packages/field-agent/src/field_agent/liveness.py: from __future__ import annotat
      import os
      from typing import Any
     @@ packages/field-agent/src/field_agent/liveness.py: class LivenessClient:
    -             ) from exc
              if resp.status_code != 200:
    +             # the status only: the body is the server's (or something on the path), never echoed
                  raise HeartbeatUnreachable(
    --                f"heartbeat returned {resp.status_code} — liveness unknown, "
    --                f"halting: {resp.text}"
    +-                f"heartbeat returned {resp.status_code} — liveness unknown, halting"
     +                f"{upstream_error(resp, 'heartbeat')} — liveness unknown, halting"
                  )
              return Heartbeat.model_validate(resp.json())
