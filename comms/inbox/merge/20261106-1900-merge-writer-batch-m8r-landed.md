# merge-writer: BATCH m8r LANDED on main (fast-forward)
Old main e125a878dd37118bb68c933741444b407be8b8bb -> new main ccab23793bc4f12eb8611624c24b0cdc808894a8 (ls-remote verified; branch batch/2026-11-06-m8r, no vehicle PR). Plain fast-forward, no force.
Gates (HIGH): source heads unchanged at push time; CI 7/7 each; reviewer verdicts naming each head (819 PASS 1659, 842 PASS 1733, 839 PWC 1731 (C1 landing order vs 828, applies to the second lander), 845 PWC 1746 (C1 compose check before setting the variable on the GB10, operating)); GX10 16/16 on ccab2379 (verifier-6, 20261106-1847); origin/main ancestor; 5 commits author+committer Don Hagell noreply; nothing under .github/.
Landed (source heads): 819 6aff87a2, 842 cca160cd, 839 524da359, 845 3f74c600.
First attempt m8 (head 62c81c76, with PR 835) FAILED GX10 15/16: lifecycle-manager test_no_operators_row_is_shipped_in_this_repository_with_the_list_exemption found docs/templates/operators.g17-template.json row don-breakglass (verifier-5, 20261106-1828). PR 835 collides with the G21 test from PR 817 (on main since m7). 835 needs a builder/architect fix (template row or test). m8 branch abandoned; m8r rebuilt without 835.
Held out: 835 (above); 836 and 840 (PWC C1 test pins unmet); 837 (C1/C2 unfixed) and 838 (needs 837 and the architect); 841, 844 (conditions unmet); 843 (CI 4 failing); 846, 847 (CI incomplete).
BLOCKER (close step): `gh pr close` on 819 842 839 845 was DENIED by the auto-mode classifier. Not worked around. Those four PRs are OPEN; coordinator or Don must close them (comment: landed via m8r, main ccab2379).

CLOSE STEP UPDATE (2026-11-07): done. All source PRs of this batch (and old 374 where named) are closed, on Don's chat approval; the earlier "blocked/pending" wording above is superseded.
