# B-COND-PR744-c97dd1c (ssl-ff-builder-8)
Condition (MEDIUM, mutant Q2: scan_secrets_text not pinned by the wall-clock bound) applied on PR branch fix/find-secrets-scale-s7-14, new head af5dc04eac8dc9b9ffdf89fc88ac0ca551a9fa74, tests only.
New test test_scan_secrets_text_counts_each_character_for_newlines_at_most_once passes a str subclass that records the span of each count() call: total counted characters must be <= len(text) and calls <= hits (2,000 hits). Work-based, no timing.
Local (PYTHONUTF8=1, services/agent-registry): test_find_secrets_scale.py 5 passed. Mutant Q2 (count from 0 per hit) now FAILS the new test (and the timing test, 34 s run). Source untouched. Re-review needed on the new head.
