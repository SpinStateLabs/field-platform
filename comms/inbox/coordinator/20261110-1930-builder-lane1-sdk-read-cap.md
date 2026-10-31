# Builder lane 1: SDK transport read cap (C-642b, Don's ruling on PR 372 C4)

- PR 409 (draft), branch fix/field-agent-read-cap-c642b, head 2c089ebbb799c9b639309d33cb29889fa66fac61. STACKED on PR 372 (base is its branch); lands after 372, then retarget to main.
- Change: AuthedClient streams replies and counts decoded bytes against MAX_RESPONSE_BYTES (1 MiB); over it raises ResponseTooLarge, fixed text, no body bytes. Covers every SDK client. FieldClient (own 64 KiB cap) unchanged.
- Tests: 8 new; mutants 6 of 6 red. field-agent 212 passed, field-core 1136, whole tools suite 53/53 files, EXIT=0.
- No `_transport.py` overlap with PRs 405, 348, 383, 399, 395, 381. ENVIRONMENT.md unchanged.
- NOT run: GX10, CI. Ask: review of 2c089eb.
