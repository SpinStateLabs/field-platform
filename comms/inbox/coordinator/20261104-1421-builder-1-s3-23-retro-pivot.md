# builder-1 S3-23 (agent-incident-retro S.pivot)
PR: https://github.com/SpinStateLabs/field-platform/pull/644 (draft), head f7c3765e.
Ran: tests/test_pivot_cost_and_caps.py 7 (4 red before); 4 mutants caught (1, 3, 2, 2 failed); defence-shield/agent-incident-retro/tests 236 passed. 2000x2000 parses: ~4,000,000 before, <= 4000 after.
Finding beyond the card: param_values returned UNCAPPED names while hostile_params returns CAPPED ones, so a pivot on a parameter name over 8192 bytes was silently missed; now fires.
Deviation: card check (b) (value differing only after byte 8192) cannot flip a verdict as written (a benign request equal to the capped hostile form classifies as hostile itself); pinned the value cap directly and tested the key-cap verdict instead.
