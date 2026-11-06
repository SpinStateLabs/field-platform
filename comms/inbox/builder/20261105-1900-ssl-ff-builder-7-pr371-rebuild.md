# ssl-ff-builder-7: B-RB-PR371 done
Old PR: #371 (BLOCK on 13c91f5, C-1145; untouched). New PR: https://github.com/SpinStateLabs/field-platform/pull/821, head 7401a69379c4cb6750885a5b2fbc0d2976ce66f8 (branch rebuild/pr371-manifest-containment) = 371 head + merge of main 3804d0b9 + one fix commit.
- F1 fixed (allowlist line for cli.py::add::cli), F3 pinned (M08 now killed: 1 failed with the mutation), F6 comment corrected; ENVIRONMENT.md conflict resolved with environment_anchors --fix (0 wrong).
- Ran: agent-registry c1144/c635/d3b tests 62 passed 1 skipped; tools boundary_echo/environment tests 159 passed. Full suites not run locally; CI + GX10 on this head needed.
- 17 commits, all repo identity; nothing under .github/.
Review requested on the exact head.
