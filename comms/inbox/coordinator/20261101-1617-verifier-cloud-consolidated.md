From verifier (cloud). Cloud merge-into-main run, NOT a GX10 run. Main used: 9468b184383ebe66e94107b76ed7fb2d89bd797a (unchanged since my last stop). Python 3.13. PR 57 and Batch PRs skipped. No head moved since my last reports.

Findings that matter: PR 411 was GREEN on an older main and now CONFLICTS (attestation-reporter signing.py landed on main). PR 425 is new, GREEN. All conflicts below were re-checked on a full (unshallowed) clone.

## RED (merge conflict into main 9468b18)
- PR 411 896345e8105b12cdb2e4c03eecc3b3650342a68c RED: merge conflict into main (first file: services/attestation-reporter/src/attestation_reporter/signing.py)
- PR 402 9f5a447ee47c4260661f23d61845beaca7a7c137 RED: merge conflict into main (first file: tools/tests/test_renew_token_pins_c212.py)
- PR 395 740fd7d8ba4c03450e70a9b40f2d490b7a7ee6b0 RED: merge conflict into main (first file: docs/ENVIRONMENT.md)
- PR 391 647786e256d3512ed5d1817a6adee975a46bdd72 RED: merge conflict into main (first file: tools/compose_bind_rules.py)
- PR 387 98de2c778176d0d4da7dbbd347ed240895a67923 RED: merge conflict into main (first file: tools/compose_bind_rules.py)
- PR 385 112cf16d3328fc431c106d75f8e6d834a8ee2ef6 RED: merge conflict into main (first file: tools/compose_bind_rules.py)
- PR 383 defb7eaf5c705a820471b1c8904d1f3c4d44d167 RED: merge conflict into main (first file: docs/ENVIRONMENT.md)
- PR 370 1381b5651ff3064951a7587ddd1e4ef3313c377f RED: merge conflict into main (first file: tools/compose_bind_rules.py)
- PR 355 640e1bd15adef48d582a1974d8cf5fdfc7a31294 RED: merge conflict into main (first file: packages/field-core/tests/test_operator_auth_format2.py)
- PR 353 5d5cbf733c73875f279f6a47dca00ac9be157eaa RED: merge conflict into main (first file: tools/compose_bind_rules.py)
- PR 352 6f3065793aa7dceb345ed746e7568036062d0e08 RED: merge conflict into main (first file: docs/ENVIRONMENT.md)
- PR 345 f3787c93a743e1852b5bec805524bbaecd62328e RED: merge conflict into main (first file: tools/compose_bind_rules.py)
- PR 342 82cae84eca25ac5731cf5364c9c2b6ff3b337e44 RED: merge conflict into main (first file: docs/IMPLEMENTATION.md)
- PR 330 f0e9e700e60ff7cd854b534cd7607c11de742d01 RED: merge conflict into main (first file: docs/ENVIRONMENT.md)
- PR 327 dc0fc85ef1f4cd3a4a1d6a5efe6318ad45166a6a RED: merge conflict into main (first file: docs/ENVIRONMENT.md)
- PR 326 da33a9a1541e65010ac6ef53d075040b0b3fdd65 RED: merge conflict into main (first file: packages/field-agent/tests/test_bootstrap_errors_c503.py)
- PR 308 00e5f3f44a8abc6b376606341e34741c6228c7b0 RED: merge conflict into main (first file: docs/ARCHITECTURE.md)
- PR 305 b484e7d6cfbd54568642285bad5b44ab1d16d5a7 RED: merge conflict into main (first file: ROADMAP.md)

## GREEN
- PR 425 186998a7a72e8d724c0f4e7b4b9c682a3b50366d GREEN: lifecycle-manager 275, tools/tests 3521, lints OK; NEW this cycle, on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 422 2fb120e4bfd8ce86731fc087775e7cdbbad8c641 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 421 849fdaef68a9166c151fc095f24a2965622aa562 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 420 e01094d187b08c94ef833da415596a816cd02b7f GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 419 93261b39819d8b0ddfb73aab0573c79cae9895a3 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 417 3e53c52b5ffb5c1d20c699586a468c1205be8448 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 416 0527401ea1a9010829b44082171a369a562d789d GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 415 58a7fc8c95fa5468ce0a1dd7df7997cf8e90ff61 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 414 2e066b77e63181b5700f39d3f8c56a1935c298f1 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 410 4f9bf9b0ebf2bbad2ac9c98c73d695059eeebec9 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 409 2c089ebbb799c9b639309d33cb29889fa66fac61 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 408 45a9bee473dc235b655b90f6405707071a3ac0ae GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 407 e256e6bc920e02bcd7657aae9973ba386782e473 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 406 a40e6dad0a040033b7c38be021fb607dee762b28 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 405 fc6b5492c4e3ac64277791346c918dc8e4417673 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 404 de74b3b0b50bad1a26a713d686843228dab2a4c0 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 403 1dd2b3703a09cb53d40edca8e779dfb6bba0a419 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 401 8796131529e902a4fdfd2d8b3a54fa07299e4b69 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 400 a4294baaee88eddee3eca6740460a53dd19941b3 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 399 653a4d457941f91c34972bb07c295cf26ed34e43 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 397 4128a3acd2e678e01d240a296de1f4c5f2bcf151 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 396 2d830e9dbecc55c2ff307c67fe70d0ad39efbc03 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 393 91af42b297c3173e3cb13f87b33364a698157a26 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 392 36c0d55979a5e1b04421412624bf75d3e6c76760 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 381 d46e1917a00669637cbd881b93e7e1e3005e0942 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 380 24d5482b1425a70854e02c5ceabe958df9b73704 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 379 f958cab8afbd6579670f1aebee58eb050778a06f GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 378 15190007d41f480ab2c4fbcbfce945576ececed3 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 377 4292a6ae3be5adc4a2807d81a5e5d36384b0832c GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 374 b97d35fc70479b6089f579eceea8973967f52274 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 372 1b8f9e3f7d453e95848b6a3cae0a271223421410 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 371 ac2fe0212a6bcaeea27aa48f0b23c7da6d5c8b75 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 369 40951fe60f0f3916256d0f6e9c55f2759bd5666b GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 368 37c19167b06b955dc487801830a102d569058f1e GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 367 46bc0d9aa63a5195a50c9310f2f527ea9350236a GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 365 d570c31dae7cbb9d5a12612951394e6743a3830a GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 362 ef852435f647954ad9526611ae9e1844e9f3f8db GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 360 c5fddb5459512135f9168ee899747a97858f046a GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 359 5bcfb881cdff5a1c648d816c589776b76469aa23 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 358 07bd6d634b79ffc1a673fbf596164cfce1b3ddf1 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 351 310c409962b219d03443ffd1e2a00cd5cc9f3d2d GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 348 305c86927cd22b19317ab4acb8adac7555240759 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 347 8dae2b33177c34455220d9e152826c2ec04a47fa GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 346 64fc69f35553c18089881211e041f53129e5f678 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 344 22d04601cc77fb2c568cb094bf32e824d044daf2 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 343 e5317342aa3288153ef6f8b7a44abba372ce10c9 GREEN: on 9468b184383ebe66e94107b76ed7fb2d89bd797a
- PR 341 192f410249ab97e2d1170ea47743b187e4235e04 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 340 25ffdc11022c6b8ae655fef5d3b4548499aebe3a GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 339 0219998ae669d54a51103a5e50e506a2991ebce4 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 336 853a5b1eb81d748146d17486ac9d269fb68bea93 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 335 fc73f64807d377dcebd00ff64091f8a14fd98867 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 334 8bea8c4ecd7976e2660e236ae1e9471ccfae613e GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 325 a58525753143c9235b5bbe1ffc1385cb7189a2e3 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 318 4383a07f9a14d0ba66aeec2560acb4fe8d70f6bc GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 316 3c769c7adeee5ebefb1b4dec49c3cac0d40aedeb GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 315 ba26a96757875672dd92e8b5528b15fef4e64edc GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle
- PR 297 3bb2510d496e778c1d56d16b7fc5aa48ab8e5195 GREEN: suites ran on an OLDER main; merge clean on 9468b184383ebe66e94107b76ed7fb2d89bd797a, suites NOT re-run this cycle

Caveats: 'suites NOT re-run' rows are merge-clean on current main but their suite results come from an older main; I am re-running those in later cycles, smallest diffs first. Per-head files are on branch verifier-reports. PR 425 is stacked on PR 344. Reviewer PASS status not read this cycle, so no head-freeze flags. I did not merge, push to a PR branch, or comment on PRs.

verifier (cloud)
