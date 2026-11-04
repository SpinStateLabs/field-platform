# Builder B-S5-23: deployment_agent manifest shapes, draft PR 697

Head e338696e on fix/deployment-agent-manifest-shapes. UNVERIFIED (no GX10).
- Claim re-checked on current main: reproduced (kill_switch string/list/null/int -> AttributeError; non-UTF-8 -> UnicodeDecodeError; CLI traceback). No open PR or comms claim touches tools/deployment_agent/manifest.py (branch scout-s4-23-manifest is ops-console).
- Failing test first: tools/tests/test_deployment_agent_manifest_shapes.py, 12 of 18 red. Fix: kill_switch must be a mapping, local_sentinel a non-blank str, OSError/UnicodeDecodeError -> ManifestError. Mutant (drop mapping check) 6 red, restored.
- Ran: new file 18 passed; with test_deployment_agent*.py + four lint tests 837 passed, 2 skipped; anchors 0 wrong. NOT run: GX10, full tools suite.
- Note: age bool/0/str and list granted_by were already refused; pinned, not changed.
