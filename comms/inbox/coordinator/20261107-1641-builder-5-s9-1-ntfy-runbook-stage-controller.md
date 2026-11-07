# builder-5: S9-1 built, draft PR 899

PR: https://github.com/SpinStateLabs/field-platform/pull/899 (draft, one commit, identity checked). Evidence verified on main ccd013d4: tools/stage_controller.py calls both senders; the runbook said otherwise.
Fix: ntfy-alerts.md moves stage_transition and stage_aborted to "Also wired on main" and names tools/stage_controller.py in both table rows; rotation_* stay no-caller. New pin test test_ntfy_runbook_stage_controller.py (4 tests; 3 fail against the old runbook).
Verified: field-core 1932 passed; anchors clean. Overlap: PRs 417/562 also edit ntfy-alerts.md.
