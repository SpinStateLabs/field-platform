VERDICT: INFORMATION on main acaf5f241f00754442c7adbbb0290769dbfe52c5 (docs proposal; nothing edited)

Reviewer Lane 15, cloud-reviewer, C-1005. UNVERIFIED: no GX10, CI not read. Method: `git show origin/main:STATE.md`, searched with the binary-text option on (the file is flagged binary by plain grep, so a plain search can miss lines).

## Objections first
1. All four lines are inside dated log entries of 2026-09-14 in the section "Current phase" (heading at STATE.md:320); each describes what was decided or planned that day, and each plan was carried out (A7b COMPLETE at :1336, Fly A9 armed at :1269). None is a live instruction (HIGH, read).
2. Rewriting a dated record changes what the record says Don decided and what ran; the safer fix is a pointer, not an edit of the old wording (my judgement; Don can overrule).

## Exact lines on main (STATE.md)
| line | text class | history or instruction | action |
|---|---|---|---|
| 1101 | within "Don's decisions 2026-09-14": "A9 go after a clean ≥ 1 h A7 soak without asking again" | history (a recorded decision, done) | keep; append a pointer |
| 1189 | "Fly A9 after a ≥ 1 h GB10 A9 soak (≥ 16:06Z)" | history (plan; Fly A9 armed at :1269) | keep |
| 1268 | "REQUIRE last after a ≥ 1 h soak" | history (plan; A7b complete at :1336) | keep |
| 1322 | "REQUIRE last, after a ≥ 1 h soak (`gb10-a7b-require.sh`)" | history (same step; read as forward text, done at :1336) | keep |
Other dated soak mentions already in the file and fine as history: :633, :877, :902, :917 (soaks that ran 59 or 61 minutes), :921, :966.

## Proposed replacement text (docs only)
1. One new line directly under the "## Current phase" heading (after line 320), in place of any edit to the four lines:
   `Soak durations in the dated entries below record what ran or was planned on that date. The standing rule since 2026-11-01 (Don, C-495): a soak is five minutes with C0 every five minutes; a 24 h scheduler soak stays 24 h.`
2. Optional, line 1101 only (it states a decision that sounds standing): append at its end `(superseded for new work by the five-minute rule, 2026-11-01)`.
3. Lines 1189, 1268 and 1322: no change.

## Where the rule is live (not STATE.md)
tasks/todo.md:477 and :624 (fixed by PR 392: "C0 every 5 minutes"), the runbook soak sites at :925, :949, :1000 (already five minutes on main), and the 24 h rows at todo.md :512, :601, :646, :674 which correctly stay.

## Conditions
Apply item 1 (and optionally 2) when the docs batch is cut; no other STATE.md edit is needed. The outside scripts that may hard-code an hour remain unchecked (C-978).

Not verified: whether the date of the five-minute rule (2026-11-01) is the date Don gave (I took it from the soak commit title on main); the outside scripts.
