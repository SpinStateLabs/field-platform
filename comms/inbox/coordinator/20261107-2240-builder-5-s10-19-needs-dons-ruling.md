# B-S10-19 report (builder-5): NOT BUILT, needs Don's ruling
No PR. The card itself says it needs Don's ruling because it flips a pinned test (tests/test_f4_served_signing.py:199 pins that ?org=Acme Corp comes back signed_via estate-key). I searched origin/comms and found no ruling on it, so I did not pick a branch.
Evidence status: on main 2bc5643e api.py still lets the org query parameter replace eng.org and then signs with the estate key (per the card; I did not re-run it since no code is changing).
Decision needed from Don (pick one):
  A (my recommendation, MEDIUM confidence): when served signing is 'on', refuse a per-request org that differs from the configured org with a fixed-text 422; unsigned drafts keep the override. Flips the pinned test; update README/SPEC estate-key row.
  B: serve that pack unsigned with a visible note instead of refusing.
  C: keep the behaviour; docs-only PR stating the standing attestation covers any org string a perimeter-secret holder supplies.
Why A: org is inside the signed bytes, so today any authenticated caller gets a valid estate-key signature over an org the estate never configured. Counter-case for C: callers legitimately render per-client packs for several orgs under one estate (not in source: I do not know whether that is a real use).
Overlap: PR 914 (S9-17) touches how the signer/org are shown in the pack; a later PR should rebase on it.
Once Don rules, re-queue as a card naming the letter.
