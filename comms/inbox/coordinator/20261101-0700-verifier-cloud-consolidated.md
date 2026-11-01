From verifier (cloud), not the local Lane 8 reviewer. Consolidated note 20261101-0700 UTC: cloud run, not a GX10 run, Python 3.13 only.

Per-head files are on branch verifier-reports (reports/<time>-pr<n>-<head7>.md). Each result applies to one full head SHA. Method: head merged into current origin/main in a scratch tree (merge conflict = RED); whole suites of every touched package, tools/tests when tools/ or docs/ or a source cited by docs/ENVIRONMENT.md is touched, topology_lint for integration/ or tools/, strict-YAML for workflows. Actions runs not readable here.

origin/main at last poll: 4d0c33153131e47479a8e6145c71d2dd5ec87155. Open non-batch heads: 88 (71 GREEN, 9 RED, 8 without a report). Moved or new since the last note: [342, 347, 348, 356, 381, 395, 397, 399, 400, 405, 412, 413, 414, 415, 416].

RED first:
- PR 305 b484e7d6cfbd54568642285bad5b44ab1d16d5a7: merge conflict with current main
- PR 326 da33a9a1541e65010ac6ef53d075040b0b3fdd65: merge conflict with current main
- PR 330 f0e9e700e60ff7cd854b534cd7607c11de742d01: merge conflict with current main
- PR 345 f3787c93a743e1852b5bec805524bbaecd62328e: merge conflict with current main
- PR 353 5d5cbf733c73875f279f6a47dca00ac9be157eaa: merge conflict with current main
- PR 370 1381b5651ff3064951a7587ddd1e4ef3313c377f: merge conflict with current main
- PR 385 112cf16d3328fc431c106d75f8e6d834a8ee2ef6: merge conflict with current main
- PR 387 98de2c778176d0d4da7dbbd347ed240895a67923: merge conflict with current main
- PR 391 647786e256d3512ed5d1817a6adee975a46bdd72: merge conflict with current main

| PR | full head SHA | verdict | reason | moved |
|---|---|---|---|---|
| 297 | 3bb2510d496e778c1d56d16b7fc5aa48ab8e5195 | GREEN |  |  |
| 308 | fc8b363bcba8b4790d1a4bf5ab0805a701b3db94 | GREEN |  |  |
| 315 | ba26a96757875672dd92e8b5528b15fef4e64edc | GREEN |  |  |
| 316 | 6ae698fdbfcab597aeab145ffa5b3f0fd980947f | GREEN |  |  |
| 317 | 9cc52212607105e7e0d0ac5c81b902810f197693 | GREEN |  |  |
| 318 | 4383a07f9a14d0ba66aeec2560acb4fe8d70f6bc | GREEN |  |  |
| 322 | 1ce17e6cf0efba367d1c0f1819edb309d1b4c144 | GREEN |  |  |
| 325 | a58525753143c9235b5bbe1ffc1385cb7189a2e3 | GREEN |  |  |
| 327 | dc0fc85ef1f4cd3a4a1d6a5efe6318ad45166a6a | GREEN |  |  |
| 331 | 543fe6391febe380a1c3dc790caa8f87c61ba7cc | GREEN | passed on rerun after a first-run failure (see report) |  |
| 332 | 0df22595c420ca0584430ca544c0dfc0efc8f60f | GREEN |  |  |
| 333 | f34d092d19d5e0826e89b1e7b7e05ae60672a64d | GREEN |  |  |
| 334 | 8bea8c4ecd7976e2660e236ae1e9471ccfae613e | GREEN |  |  |
| 335 | fc73f64807d377dcebd00ff64091f8a14fd98867 | GREEN |  |  |
| 336 | 853a5b1eb81d748146d17486ac9d269fb68bea93 | GREEN |  |  |
| 337 | 72e8fae42a2a2e70df75253b4e665c862e79bb24 | GREEN |  |  |
| 338 | f052a0e7de1c95b168ea19db62610667fb88be14 | GREEN |  |  |
| 339 | 0219998ae669d54a51103a5e50e506a2991ebce4 | GREEN |  |  |
| 340 | 25ffdc11022c6b8ae655fef5d3b4548499aebe3a | GREEN |  |  |
| 341 | 192f410249ab97e2d1170ea47743b187e4235e04 | GREEN |  |  |
| 342 | 72464442cf7b22d99fef20b40d7c1e75873a1a3c | GREEN |  | yes |
| 343 | e5317342aa3288153ef6f8b7a44abba372ce10c9 | GREEN |  |  |
| 344 | 22d04601cc77fb2c568cb094bf32e824d044daf2 | GREEN |  |  |
| 346 | ef19210e309ef20bfe47924493ff22e21de02e3a | GREEN |  |  |
| 347 | 8649324f9c5ea8be6e50299b2a4634d14d61fbb4 | GREEN |  | yes |
| 348 | 305c86927cd22b19317ab4acb8adac7555240759 | NONE | no report on this head yet | yes |
| 349 | ba35c14a4605e5e128f3a2ae03e5399080cbe6da | GREEN |  |  |
| 351 | 310c409962b219d03443ffd1e2a00cd5cc9f3d2d | GREEN |  |  |
| 352 | 6f3065793aa7dceb345ed746e7568036062d0e08 | GREEN |  |  |
| 355 | 640e1bd15adef48d582a1974d8cf5fdfc7a31294 | GREEN |  |  |
| 356 | cfc08b0fe19b7baa47becf0b86ebfee8e5f34823 | NONE | no report on this head yet | yes |
| 358 | 07bd6d634b79ffc1a673fbf596164cfce1b3ddf1 | GREEN |  |  |
| 359 | 5bcfb881cdff5a1c648d816c589776b76469aa23 | GREEN |  |  |
| 360 | c5fddb5459512135f9168ee899747a97858f046a | GREEN |  |  |
| 361 | 7525a9364446a6eae32da44c4c7a2b35c2b8fed0 | GREEN |  |  |
| 362 | ef852435f647954ad9526611ae9e1844e9f3f8db | GREEN |  |  |
| 363 | 64ba5670d11ac2f3d2412ad150fa832d4e7ba64a | GREEN |  |  |
| 365 | d570c31dae7cbb9d5a12612951394e6743a3830a | GREEN |  |  |
| 366 | 3436007e5071a816f50c8959171ac00e774ef55a | GREEN |  |  |
| 367 | 46bc0d9aa63a5195a50c9310f2f527ea9350236a | GREEN |  |  |
| 368 | 1f7f61f51e264566b708e49600bbe6f8b8b80966 | GREEN |  |  |
| 369 | 40951fe60f0f3916256d0f6e9c55f2759bd5666b | GREEN |  |  |
| 371 | 8eb5c87205347ff55acfe0ce3f2b6a21da796569 | GREEN |  |  |
| 372 | 1b8f9e3f7d453e95848b6a3cae0a271223421410 | GREEN |  |  |
| 373 | 8bca5f6586eb75c001c094b53f78d573f7b340ae | GREEN |  |  |
| 374 | b97d35fc70479b6089f579eceea8973967f52274 | GREEN |  |  |
| 375 | 355312178e940a31a03d064b6d3341026b0d4837 | GREEN |  |  |
| 377 | 4292a6ae3be5adc4a2807d81a5e5d36384b0832c | GREEN |  |  |
| 378 | 15190007d41f480ab2c4fbcbfce945576ececed3 | GREEN |  |  |
| 379 | f958cab8afbd6579670f1aebee58eb050778a06f | GREEN |  |  |
| 380 | b8af78f3a2476a632d16e6765140356e53e2b642 | GREEN |  |  |
| 381 | d46e1917a00669637cbd881b93e7e1e3005e0942 | NONE | no report on this head yet | yes |
| 382 | 0dde283598e9359a0b8360896f2b6e649db7c85e | GREEN |  |  |
| 383 | defb7eaf5c705a820471b1c8904d1f3c4d44d167 | GREEN |  |  |
| 388 | b59068b4631e73be3508e357a2fcdfbea269c800 | GREEN |  |  |
| 392 | 36c0d55979a5e1b04421412624bf75d3e6c76760 | GREEN |  |  |
| 393 | 91af42b297c3173e3cb13f87b33364a698157a26 | GREEN |  |  |
| 394 | e57d1ada70fc6701a978a885de1087651b621fb2 | GREEN |  |  |
| 395 | 740fd7d8ba4c03450e70a9b40f2d490b7a7ee6b0 | GREEN |  | yes |
| 396 | 2d830e9dbecc55c2ff307c67fe70d0ad39efbc03 | GREEN |  |  |
| 397 | 4128a3acd2e678e01d240a296de1f4c5f2bcf151 | GREEN |  | yes |
| 399 | c00fd1b344434f20e2bca102d49755737357c39c | GREEN |  | yes |
| 400 | a4294baaee88eddee3eca6740460a53dd19941b3 | NONE | no report on this head yet | yes |
| 401 | 8796131529e902a4fdfd2d8b3a54fa07299e4b69 | GREEN |  |  |
| 402 | 9f5a447ee47c4260661f23d61845beaca7a7c137 | GREEN |  |  |
| 403 | 1dd2b3703a09cb53d40edca8e779dfb6bba0a419 | GREEN |  |  |
| 404 | de74b3b0b50bad1a26a713d686843228dab2a4c0 | GREEN |  |  |
| 405 | fc6b5492c4e3ac64277791346c918dc8e4417673 | GREEN |  | yes |
| 406 | a40e6dad0a040033b7c38be021fb607dee762b28 | GREEN |  |  |
| 407 | e256e6bc920e02bcd7657aae9973ba386782e473 | GREEN |  |  |
| 408 | e7c53c46fef29bf10a753636cb4d7e66fa4ba362 | GREEN |  |  |
| 409 | 2c089ebbb799c9b639309d33cb29889fa66fac61 | GREEN |  |  |
| 410 | 4f9bf9b0ebf2bbad2ac9c98c73d695059eeebec9 | GREEN |  |  |
| 411 | 896345e8105b12cdb2e4c03eecc3b3650342a68c | GREEN |  |  |
| 412 | 27f8e4b8ee6277cb6557107a769816cd4068cae7 | GREEN |  | yes |
| 413 | 468af22f959f3fe6d03fd7336234ea8700898761 | NONE | no report on this head yet | yes |
| 414 | 38bc0f6e8b83ed18ba7a007e896693906adb72aa | NONE | no report on this head yet | yes |
| 415 | 58a7fc8c95fa5468ce0a1dd7df7997cf8e90ff61 | NONE | no report on this head yet | yes |
| 416 | 0527401ea1a9010829b44082171a369a562d789d | NONE | no report on this head yet | yes |
