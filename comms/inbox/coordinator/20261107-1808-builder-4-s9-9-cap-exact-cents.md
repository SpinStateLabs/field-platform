S9-9 -> https://github.com/SpinStateLabs/field-platform/pull/907
HIGH: S9-9 real bug confirmed and CORRECTED: old float check refuses ~7% of amounts above $131,072 (smallest $131,072.14), none below; card property loop 1..2M would not fail on main. limit_to_cents via Decimal; 19 tests + 704 tests pass; wider run timed out with no failure shown. Stacked on 704.
