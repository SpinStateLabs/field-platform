builder-1: B-REBUILD-PR443 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/568 "rebuild of #443", branch rebuild/pr443-422-field-name, head 77e1ec8432700aa69d7592acd11b70810fcb6b22 on origin/main 97dcfec1. Old head 98fc9151 untouched.
MORE THAN CONFLICT RESOLUTION (hand merge; GX10 16/16 on old head does not cover it, needs a re-read): main already carries parts of this PR in other form (6385f877, C-1183, C-1189). Commit 1 redacted_loc unchanged (=). Commit 2 federation-broker: replaced main's inline _known_names/REDACTED_NAME loop with the PR's redacted_loc helper (PR intent). Commit 3 agent-registry: took main's api.py and test edits; only the new test_422_no_echo_agent_registry_c1114.py remains. Commit 4 guard: took main's file (already AST + serving-app guard + behaviour tests), added builds_app (AST), MEASURED/NOT_YET disjoint-and-complete test, per-service no_echo test existence, scan negative/positive cases.
Ran: field-core 1552 passed 1 skipped; agent-registry 319; federation-broker 197; guard + environment-doc tests 123 passed; anchors 0 wrong.
Range-diff:
1:  ed8b68b1 = 1:  25b03caa field-core: redacted_loc, the location of a 422 error without a name the caller chose (C-1128)
2:  be07987e ! 2:  ae5965d5 federation-broker: a 422 no longer repeats a field name the caller sent (C-1128, C-1123 F1)
    @@ services/federation-broker/src/federation_broker/api.py: from fastapi.responses
      
      from field_core.authn import install as install_authn
      from field_core.buildinfo import build_sha
    +-from field_core.http_errors import REDACTED_NAME, _known_names
     +from field_core.http_errors import redacted_loc
      
      from federation_broker import __version__
    @@ services/federation-broker/src/federation_broker/api.py: def create_app(engine:
          ) -> JSONResponse:
              # FastAPI's default 422 quotes every error's ``input`` — a contract's
              # key field can be a pasted PRIVATE key, and a ``missing`` error quotes
    --        # the whole body. Same response shape, minus ``input``.
    +-        # the whole body. Same response shape, minus ``input``. A string in ``loc`` that is not a declared name is a
    +-        # caller-chosen key, so it is replaced too (C-1128, reviewer C-1123 F1); the message text is kept, because
    +-        # this service's validators write explanatory messages (whether that text may stay is F3, Don's decision).
    +-        known = _known_names(request.app)
     -        errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    +-        for e in errors:
    +-            e["loc"] = [p if (not isinstance(p, str) or p in known) else REDACTED_NAME for p in e.get("loc", ())]
     +        # the whole body. Same response shape, minus ``input``. A field NAME the
     +        # caller sent lands in ``loc``: it is replaced by the field-core helper
     +        # (C-1128). The messages the contract validators write stay (C-1123 F3
3:  55e2d43c < -:  -------- agent-registry: install the field-core 422 handler (C-1128, C-1123 F1)
4:  98fc9151 < -:  -------- tests: the 422 guard reads the syntax tree and ties its lists to the services (C-1128, C-1123 F2)
-:  -------- > 3:  6fc10f48 agent-registry: install the field-core 422 handler (C-1128, C-1123 F1)
-:  -------- > 4:  77e1ec84 tests: the 422 guard reads the syntax tree and ties its lists to the services (C-1128, C-1123 F2)
