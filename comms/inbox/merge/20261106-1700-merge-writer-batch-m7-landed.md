# merge-writer: BATCH m7 LANDED on main (fast-forward)
Old main 117469db324337529025e530c27d8dacbb2af824 -> new main e125a878dd37118bb68c933741444b407be8b8bb (ls-remote verified; branch batch/2026-11-06-m7, no vehicle PR). Plain fast-forward, no force.
Gates (HIGH): source heads unchanged at push time; CI 7/7 on each source; reviewer verdicts naming each head (817 PWC delta 0709, 826 PWC 0636, 832 PWC 0923, 833 PWC 1138, 761 PASS 1235; PWC conditions were CI/GX10 only, no open COND card); GX10 16/16 on e125a878 (verifier-5, 20261106-1636); origin/main ancestor; 7 commits author+committer Don Hagell noreply; nothing under .github/.
Landed (source heads): 817 9f9642d5, 826 bf410d51, 832 9b775755 (cherry-picked own commit above 826), 833 7a87c163, 761 533e68db.
Held out: 818 (CONFLICTING; rebase card B-G22-rebase-818-827), 760 (CI 4 failing), 819/828/825 PWC or draft. Other PASS heads without per-PR GX10 (830, 831, 824, 823, 787, 768, 728, 725 and the PASS drafts 762-785) are m8 candidates, not taken.
Closed (2026-11-06, on Don's chat approval after the classifier first denied it): PRs 817 826 832 833 761 and old 374 (superseded by 818), each with a pointer comment.
Not done: m7b (818+827 after builder rebases and a new reviewer PASS on each rebased head).
