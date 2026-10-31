VERDICT: INFORMATION on main acaf5f241f00754442c7adbbb0290769dbfe52c5 (list for builder card C-911; no code verdict)

Reviewer Lane 15, cloud-reviewer, C-978. UNVERIFIED: no GX10, CI not read. Method: every tracked file naming "soak" on main acaf5f2, then every line in docs, tasks, STATE.md and the READMEs that states a soak or C0 duration. Rule applied: soak periods five minutes; C0 every five minutes (C-495); 24 h soaks stay.

## Objections first
1. The card names lines 477 and 624; both are right and are not the only ones: the historical log STATE.md also carries the old one-hour wording as Don's standing instruction and as forward-looking steps (below). Whether a dated log entry should be rewritten is a decision, not a fix (HIGH).
2. The outside-repository scripts the runbook names (`gb10-a7-soak.sh`, `gb10-a7-arm.sh` and others, runbook :927-928) may hard-code one hour or 86400 seconds; no text in this repository settles it (not verified).

## Lines that still disagree with the rule
| file:line | text (class) | fix |
|---|---|---|
| tasks/todo.md:477 | "≥ 5 min soak with C0 every 15 minutes" | C0 every five minutes (a 15-minute cadence cannot run inside a five-minute window) |
| tasks/todo.md:624 | "Soak ≥ 5 min with C0 every 15 minutes" | same |
| STATE.md:1101 | Don's decision of a past date: "A9 go after a clean ≥ 1 h A7 soak without asking again" | a standing go worded with the old duration; note the new rule beside it rather than rewrite the dated record |
| STATE.md:1189 | "≥ 1 h GB10 A9 soak" (a plan step) | five minutes if the step is still live |
| STATE.md:1268 | "a ≥ 1 h soak" | same |
| STATE.md:1322 | "after a ≥ 1 h soak (`gb10-a7b-require.sh`)" (a REQUIRE step) | five minutes if live; this one reads as a forward instruction |

## Lines that agree or are exempt (no action)
- Five-minute soaks: docs/runbooks/v1.2-deploy-rollback.md:925, :949, :1000; tasks/todo.md:282, :426, :440, :630 ("5-minute soak"); tasks/next-session-phase-f.md:60.
- 24 h soaks that stay: tasks/todo.md:512, :601, :646, :674 (the lifecycle, crosswalk and witness scheduler soak, ≥ 25 h at the 86400 s defaults).
- No duration, depends on A7's: runbook:968 and todo.md:442 ("after a clean A7 soak"); services/sealed-ledger/README.md:283 ("after a soak in which the unsigned count stops"); integration/demo/docker-compose.yml:145.
- Dated history, not an instruction: STATE.md:633, :877, :902, :917 (soaks that ran 59 or 61 minutes), :921, :966 (the 24 h interval note).
- PR 290's three files (runbook, tasks/next-session-phase-f.md, tasks/todo.md) are on main (the BZ2 soak commit); they now carry the five-minute text, with the two C0 lines above unchanged.
- PR 382 (open) adds the soak override text for the 24 h scheduler soak and keeps the five-minute rule for others.

## Conditions
1. C-911: fix todo.md:477 and :624 (five-minute C0). 2. Decide STATE.md:1101, :1189, :1268, :1322 (add a note, or reword the forward-looking ones). 3. Check the outside scripts for a hard-coded hour.

Not verified: the outside scripts, any STATE.md text not matched by the word "soak" (the file is binary-flagged by grep; matches taken with the text option off, so lines may be missed).
