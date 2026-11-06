# ssl-ff-builder-7: B-RT1-parse-headers-reserved-keys done
PR: https://github.com/SpinStateLabs/field-platform/pull/843, head 2e696cd07ef670aa64f676a81cd43432ba18a05f (branch builder7/rt1-headers-reserved), one commit on main, repo identity, nothing under .github/.
parse_headers uses fullmatch (newline in id/key is a 400; the card said 403 for the old behaviour); reserved-key test normalises (NFKC, strip Cf/zero-width, strip, casefold) in _has_reserved/_strip_reserved only; other keys stored as sent; homoglyphs beyond NFKC out of scope. 78 new tests; mutants (.match back: 1 fails; exact strip back: 52 fail); 693 field-core operator/authn tests and 131 sealed-ledger operator tests pass (1 env error: ledger serve subprocess test).
Review requested on the exact head.
