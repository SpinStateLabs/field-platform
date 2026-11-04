S6-23 crosswalk CLI file errors. PR #722 (draft). 30 tests (26 fail on old src), 9 mutants (8 killed, 1 equivalent), suite 398 pass, lints pass.
Atomic pack write; output paths checked before collect_evidence; NUL path named explicitly (is_dir() is False not an error); options now str (click stats Path).
