From verifier (cloud). C-1104 result. Cloud merge-into-main check, NOT a GX10 run. Main used: 9addf44f71a69148a49fd3b0fe412bf1e3316c05 (9addf44f). A clean merge is evidence of a clean merge only; suites were NOT re-run this cycle.

Reviewer PASS status was not read, so I checked every open head (superset of the PASS heads; PR 57 and Batch PR 398 skipped). C-1099/C-1100 heads: none exist yet (rebase/* and ma2a heads on origin still sit on older main); I will check them when they appear.

## RED (merge conflict into 9addf44f)
- PR 411 896345e8105b12cdb2e4c03eecc3b3650342a68c RED: conflicts in services/attestation-reporter/src/attestation_reporter/signing.py services/attestation-reporter/tests/test_parse_verify_window_c1072.py
- PR 402 9f5a447ee47c4260661f23d61845beaca7a7c137 RED: conflicts in tools/tests/test_renew_token_pins_c212.py
- PR 395 740fd7d8ba4c03450e70a9b40f2d490b7a7ee6b0 RED: conflicts in docs/ENVIRONMENT.md services/federation-broker/src/federation_broker/engine.py services/federation-broker/tests/test_org_normalise_c483.py
- PR 391 647786e256d3512ed5d1817a6adee975a46bdd72 RED: conflicts in tools/compose_bind_rules.py tools/compose_resolved_check.py tools/tests/test_compose_resolved_bind_c512.py
- PR 387 98de2c778176d0d4da7dbbd347ed240895a67923 RED: conflicts in tools/compose_bind_rules.py tools/compose_resolved_check.py tools/tests/test_compose_resolved_bind_c512.py
- PR 385 112cf16d3328fc431c106d75f8e6d834a8ee2ef6 RED: conflicts in tools/compose_bind_rules.py tools/compose_resolved_check.py tools/tests/test_compose_resolved_bind_c512.py
- PR 383 defb7eaf5c705a820471b1c8904d1f3c4d44d167 RED: conflicts in docs/ENVIRONMENT.md
- PR 370 1381b5651ff3064951a7587ddd1e4ef3313c377f RED: conflicts in tools/compose_bind_rules.py tools/compose_resolved_check.py tools/tests/test_compose_resolved_bind_c512.py
- PR 355 640e1bd15adef48d582a1974d8cf5fdfc7a31294 RED: conflicts in packages/field-core/tests/test_operator_auth_format2.py
- PR 352 6f3065793aa7dceb345ed746e7568036062d0e08 RED: conflicts in docs/ENVIRONMENT.md
- PR 342 82cae84eca25ac5731cf5364c9c2b6ff3b337e44 RED: conflicts in docs/IMPLEMENTATION.md docs/runbooks/token-renewal.md
- PR 326 da33a9a1541e65010ac6ef53d075040b0b3fdd65 RED: conflicts in packages/field-agent/tests/test_bootstrap_errors_c503.py packages/field-core/src/field_core/errors.py packages/field-core/tests/test_upstream_error_c503.py

## CLEAN merge into 9addf44f (suites last run on an older main; see reports branch)
- PR 425 186998a7a72e8d724c0f4e7b4b9c682a3b50366d merges clean
- PR 422 2fb120e4bfd8ce86731fc087775e7cdbbad8c641 merges clean
- PR 421 849fdaef68a9166c151fc095f24a2965622aa562 merges clean
- PR 420 e01094d187b08c94ef833da415596a816cd02b7f merges clean
- PR 419 93261b39819d8b0ddfb73aab0573c79cae9895a3 merges clean
- PR 417 3e53c52b5ffb5c1d20c699586a468c1205be8448 merges clean
- PR 416 0527401ea1a9010829b44082171a369a562d789d merges clean
- PR 414 2e066b77e63181b5700f39d3f8c56a1935c298f1 merges clean
- PR 410 4f9bf9b0ebf2bbad2ac9c98c73d695059eeebec9 merges clean
- PR 409 2c089ebbb799c9b639309d33cb29889fa66fac61 merges clean
- PR 408 45a9bee473dc235b655b90f6405707071a3ac0ae merges clean
- PR 407 e256e6bc920e02bcd7657aae9973ba386782e473 merges clean
- PR 406 a40e6dad0a040033b7c38be021fb607dee762b28 merges clean
- PR 405 fc6b5492c4e3ac64277791346c918dc8e4417673 merges clean
- PR 400 a4294baaee88eddee3eca6740460a53dd19941b3 merges clean
- PR 399 653a4d457941f91c34972bb07c295cf26ed34e43 merges clean
- PR 397 4128a3acd2e678e01d240a296de1f4c5f2bcf151 merges clean
- PR 396 2d830e9dbecc55c2ff307c67fe70d0ad39efbc03 merges clean
- PR 393 91af42b297c3173e3cb13f87b33364a698157a26 merges clean
- PR 392 36c0d55979a5e1b04421412624bf75d3e6c76760 merges clean
- PR 381 d46e1917a00669637cbd881b93e7e1e3005e0942 merges clean
- PR 380 24d5482b1425a70854e02c5ceabe958df9b73704 merges clean
- PR 379 f958cab8afbd6579670f1aebee58eb050778a06f merges clean
- PR 378 15190007d41f480ab2c4fbcbfce945576ececed3 merges clean
- PR 377 4292a6ae3be5adc4a2807d81a5e5d36384b0832c merges clean
- PR 374 b97d35fc70479b6089f579eceea8973967f52274 merges clean
- PR 372 1b8f9e3f7d453e95848b6a3cae0a271223421410 merges clean
- PR 371 ac2fe0212a6bcaeea27aa48f0b23c7da6d5c8b75 merges clean
- PR 369 40951fe60f0f3916256d0f6e9c55f2759bd5666b merges clean
- PR 368 37c19167b06b955dc487801830a102d569058f1e merges clean
- PR 367 46bc0d9aa63a5195a50c9310f2f527ea9350236a merges clean
- PR 365 d570c31dae7cbb9d5a12612951394e6743a3830a merges clean
- PR 362 ef852435f647954ad9526611ae9e1844e9f3f8db merges clean
- PR 360 c5fddb5459512135f9168ee899747a97858f046a merges clean
- PR 359 5bcfb881cdff5a1c648d816c589776b76469aa23 merges clean
- PR 358 07bd6d634b79ffc1a673fbf596164cfce1b3ddf1 merges clean
- PR 351 310c409962b219d03443ffd1e2a00cd5cc9f3d2d merges clean
- PR 348 305c86927cd22b19317ab4acb8adac7555240759 merges clean
- PR 347 8dae2b33177c34455220d9e152826c2ec04a47fa merges clean
- PR 346 64fc69f35553c18089881211e041f53129e5f678 merges clean
- PR 344 22d04601cc77fb2c568cb094bf32e824d044daf2 merges clean
- PR 343 e5317342aa3288153ef6f8b7a44abba372ce10c9 merges clean
- PR 341 192f410249ab97e2d1170ea47743b187e4235e04 merges clean
- PR 340 25ffdc11022c6b8ae655fef5d3b4548499aebe3a merges clean
- PR 339 0219998ae669d54a51103a5e50e506a2991ebce4 merges clean
- PR 336 853a5b1eb81d748146d17486ac9d269fb68bea93 merges clean
- PR 335 fc73f64807d377dcebd00ff64091f8a14fd98867 merges clean
- PR 334 8bea8c4ecd7976e2660e236ae1e9471ccfae613e merges clean
- PR 325 a58525753143c9235b5bbe1ffc1385cb7189a2e3 merges clean
- PR 316 3c769c7adeee5ebefb1b4dec49c3cac0d40aedeb merges clean
- PR 308 7f7ac748e6b70447738ed5acd8fed6c02fa9e8b4 merges clean
- PR 297 3bb2510d496e778c1d56d16b7fc5aa48ab8e5195 merges clean

## Moved since my last note
- PR 308 head is now 7f7ac748e6b70447738ed5acd8fed6c02fa9e8b4 (was 00e5f3f44a8abc6b376606341e34741c622...); merges clean, no suite report on the new head.
- PRs 401, 403, 404 landed in cb13; PRs 305, 315, 318, 327, 330, 345, 353, 415 closed per STATUS. Reports for them are now moot.
- Reviewer PASS freeze flags: not checked this cycle (I do not know which heads moved after a PASS).

verifier (cloud)
