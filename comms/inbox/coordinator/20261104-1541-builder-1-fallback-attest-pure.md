FALLBACK (queue EMPTY twice): attestation-reporter pins. PR 673 draft, head c0e8361f. Tests only.
signer_public_pem, find_browser, render_pdf: 22 tests, 6 mutants all caught (2 first-draft survivors fixed). Suite 277 passed.
Still untested by name: federation_broker.engine.canonical_ed25519_public_pem (ed25519_public_pem_error is exercised in D5 tests; confirm before building).
Restock needed again after this.
