FALLBACK 2: field-agent extract_usage pins. PR 674 draft, head 2d407f37. Tests only.
18 tests, 6 mutants all caught. field-agent suite 224 passed, 1 known sandbox failure (test_canary_agent halt, also red on unmodified main).
Observed, not pinned: int() accepts float/bool token counts and passes negatives; a stricter meter would refuse them (proposal for a future card).
Queue still EMPTY. Remaining untested-by-name candidates: sealed_ledger.filters.parse_instant, witness.require_https, check_anchor, retention_check, agent_registry.redaction.find_secrets/redact_text (indirectly covered via scan_secrets_text), claude_approver.config.resolve_action/read_secret_file, lifecycle api.run_sweep.
