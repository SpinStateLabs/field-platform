# Builder Lane 1 (fork): PR 322 Don round 3 done, new head 6ac0f8e (UNVERIFIED on the GX10)

- PR 322 (open, draft, unmerged: checked), branch `fix/federation-org-normalise-c483`, head `6ac0f8e6b414ac1138a7e52961703e5e5cd1c865`, new commit on 5ff3df4. Identity Don Hagell, trailers present, no force-push.
- Per Don's ruling (round 3): joiners and invisible marks stay merged; the collision is documented. README section "Org-name matching: the joiner collision" (false 409, never a bypass, stored name unchanged). Tests: Persian ZWNJ, Hindi ZWJ conjunct, ASCII ZWJ/ZWNJ equal the plain name, second save refused; README wording pinned. No production change.
- Tests: federation-broker 185 passed EXIT=0; whole tools suite (minus helper estate_harness.py) 3120 passed, 6 skipped, EXIT=0, run on the tree before the final test/README edit (that edit touched only the README and the new test file). Mutants 7/7 red.
- NOT run: GX10, CI on this head, a real multi-process race, demo.sh.
- Ask: delta review (docs and tests only).
