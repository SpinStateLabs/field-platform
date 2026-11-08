# fp-builder-b: B-S10-32
PR: https://github.com/SpinStateLabs/field-platform/pull/965 (draft). Head a626c7e7d79a7f4e0640b40785ce76b4a32a243b from origin/main; author and committer Don Hagell noreply (audited). Tests only.
Ran (relative PYTHONPATH=src, import path confirmed in my clone): new file 35 pass; mutants delete claude-user row and urlquery row, 1 red each; agent-incident-retro suite 262 pass 2 skipped; boundary-echo + docs-cite lints 63 pass.
Recorded not fixed: substring matching; markers_for/intermediary_for skip bounded().
Could not verify: GX10 16/16.
