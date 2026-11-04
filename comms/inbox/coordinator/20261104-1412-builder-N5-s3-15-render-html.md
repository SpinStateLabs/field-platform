# Builder builder-N5: B-S3-15

PR 637 (draft), branch test/attestation-render-html-escaping-s3-15, head 5cb1f680d2a00e523f2302b3343702e13db82ca9, base main b963407a. UNVERIFIED: no GX10, CI just started.

Scout claims re-checked on main: render_html escapes 16 free-text sites; only the signer was tested; no '<script' in tests. Tests only; render.py unchanged. New tests/test_render_html_escaping.py, 22 cases.

Ran: new file 22 passed; attestation-reporter suite 277 passed; environment_anchors clean; the four lint tests 261 passed (c57 baseline gone on this main). Mutants: esc removed on m.source_query red (2), on w.note red (2); restored.

FINDING (LOW, not fixed, tests-only card): render.py integrity class 'integrity-<first token of m.value>' is unescaped. Engine only produces 'INTACT' or 'BROKEN — <reason>' so ledger text never reaches it; a hand-built Metric value like "INTACT'><script>" (no space) would inject. render_html is only called with engine-built packs (cli.py, api.py). Not pinned (would pin unsafe behaviour).

Decisions needed: add esc() on the class token (one line, separate card), or leave. Reviewer other than the author.
