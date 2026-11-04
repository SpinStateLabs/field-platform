# builder-1 S4-10 (lifecycle-manager engine path segments)
PR: https://github.com/SpinStateLabs/field-platform/pull/658 (draft), head 528aceb8.
Ran: tests/test_path_segments_encoded.py 32 (30 red on the original engine, verified after a fixture fix; 2 controls); 8 mutants all caught (10 each for the six sites, 14 dot-segment, 16 safe="/"); services/lifecycle-manager/tests 301 passed.
Beyond the card: quote() leaves '.'/'..' unencoded, so those two ids are spelled %2E / %2E%2E (otherwise still a dot-segment).
FINDING NOT FIXED (needs its own item): services/spend-governor/src/spend_governor/provisioning.py:83 builds /rate-limits/{limits.agent_id} (and its GET) with an unencoded f-string, reached via lifecycle provision's load_rate_limits. Same class, different package.
