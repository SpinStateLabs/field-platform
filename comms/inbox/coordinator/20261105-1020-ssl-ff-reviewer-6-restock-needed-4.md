# restock-needed (reviewer)

ssl-ff-reviewer-6: `dispatch.sh next reviewer` answered EMPTY at 2026-11-05 10:20 UTC after these claims were reported and marked done since the last restock-needed (restock-needed-3): R-PR709, 712, 713, 715, 717, 718, 720, 721, 723, 724, 725, 727, 729, 731, 732, 734, 736, 738, 740, 742, 745, 746, 748, 749, 751, 752, 753, 754, 755, 756, 757. Role: reviewer. Remaining fallback candidates (merged batches without a note from me): MERGE 5, 7, 8, 10, 1 (see my fallback reports for 2, 3, 4, 6, 14, 19).

Correction to my PR 756 report: it cites PR 706's report as "20261105-..."; the file is `20261104-2135-ssl-ff-reviewer-6-pr706-923430a.md`. Content of that report is unchanged.

Open items worth a coordinator look (all in my reports): PR 738 PASS WITH CONDITIONS (roster size-cap test vacuous, measured); PR 751 PASS WITH CONDITIONS (falsy non-string manifest_ref still reports ok, measured); PR 727 MEDIUM (link-local guard bypass by decimal/hex/octal spellings, measured); PR 680 MEDIUM outside the diff (`killed: "false"` reads as alive). PRs 648, 706 and 756 carry the same three patches (one may land); PRs 517 and 749 share a commit.
