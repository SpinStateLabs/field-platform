S6-11 federation lone surrogate. PR #711 (draft). 19 tests (11 fail on old src), 7 mutants killed, suite 210 pass, lints pass.
Card corrected: plain str fields were already 422; the real holes are list entries + contract_ref (500; lists write the row first) and request_summary/signature/manifest dicts (accepted).
