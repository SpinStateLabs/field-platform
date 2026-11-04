# builder-1 S4-7 (delegation-authority mint scope + /oauth/introspect cap)
PR: https://github.com/SpinStateLabs/field-platform/pull/655 (draft), head 8d0c7ea7.
Ran: tests/test_mint_request_scope_and_body_bounds.py 24 (16 red before); 9 mutants all caught (7, 2, 7, 1, 1, 3, 1, 1, 1 failed; the declared-Content-Length fast path needed a stub-request test since the streamed cap alone gives the same 413); services/delegation-authority/tests 281 passed (incl. c1114 no-echo, oauth_introspect, redteam_mint_matrix).
Decision for Don: limits are the card's suggestions (100 scopes, 200 chars, 16 KiB); scope entries are now stored stripped and de-duplicated; DelegationToken.scope in field-core left untouched.
Other: #590 (never commented) got its one comment for the main-side lint (fixed on main).
