S6-7 registry docs vs code. PR #707 (draft). Text only + 8 tests (three modes side by side + doc pins), 2 mutants killed, suite 319 pass, lints pass.
Card error corrected: no FIELD_OPERATOR_MODE variable; mode = FIELD_OPERATOR_REQUIRE (enforce) / FIELD_OPERATOR_REGISTRY (log-only) / neither (off). Log-only half run.
