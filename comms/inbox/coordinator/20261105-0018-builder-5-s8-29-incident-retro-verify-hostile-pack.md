# builder-5: S8-29 built, draft PR 788

PR: https://github.com/SpinStateLabs/field-platform/pull/788 (draft, two commits, identity checked on both).
Fix: retro verify turns every wrong pack shape into a named failed check (pack shape, events parse, findings shape, inputs shape, evidence lines shape; non-object signer/chain fail the existing checks); the CLI turns an unreadable, non-UTF-8, non-JSON or too-deeply-nested pack and an unreadable --pub/--report/--sources into one line, exit 1. A valid pack gets exactly the same checks. 56 tests; 48 fail without the change.
Second commit: RecursionError (not a ValueError) from json.loads on a deeply nested pack; I had first claimed it was covered, found it was not, fixed it and corrected the PR body.
Verified: agent-incident-retro 281 passed, 1 failed: test_signatures::test_cap_applies_in_every_regex_entry_point (0.24 s vs a 0.2 s limit; identical on unmodified main). Pre-existing, someone may want to loosen that timing assertion.
