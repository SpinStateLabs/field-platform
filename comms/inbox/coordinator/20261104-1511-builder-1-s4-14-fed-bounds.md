S4-14 federation-broker text bounds. PR 662 draft, head af3af8b3.
Names 256, lists 100, signature 512; whitespace-only org/scope/data_class refused (not stripped). Manifests untouched.
Tests: test_text_bounds.py 20 (18 red before). Mutants 5/5 caught. Suite 211 passed.
Decision for Don: (1) C-483 test pinned whitespace-only org as accepted; changed to expect ValueError per card. (2) Bounds apply to stored rows on list; oversized pre-existing rows would fail to list, unknown if any exist. (3) limits 256/100/512 are my picks.
