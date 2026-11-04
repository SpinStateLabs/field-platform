# builder-5: G19 built, draft PR 760

PR: https://github.com/SpinStateLabs/field-platform/pull/760 (draft, one commit, identity checked, flags untouched).
Confirmed still open on main (no open PR). estate_probe, phase_g_check, renew_token: with an operator key present a non-https base must be loopback (RFC1918 refused); https, --allow-plaintext and the secret-alone private allowance unchanged. 104 tests; mutant fails 9.
Verified: related tools tests 785 passed; env-doc lints 98 passed.
Risk to note: anything running these tools with a key against a private plaintext base now needs https or --allow-plaintext; runbooks not audited for such an invocation.
