S5-5 field-core alerts fullmatch + NUL path. PR 681 draft, head 7de0fd63.
Evidence verified. Patterns end in \Z (not $): right under match and fullmatch; TOPIC_RE is public so not "drop ^/$". NUL path: ValueError is raised in click's Path option stat during parsing (before the command), so --out is now str -> Path in the handler, ValueError caught -> exit 2.
Tests: test_alerts_fullmatch.py 21 (9 red before), incl. content_problem pins. Mutants 8/8 caught. field-core suite 1565 passed; lint 225 passed; anchors 0 wrong.
Decision for Don: topic/token from env are stripped, so only the render fields (estate/subject/detail) are reachable; the card's env-dict test for topic/token newline is impossible. --out type changes in --help; other Path options share the NUL behaviour.
