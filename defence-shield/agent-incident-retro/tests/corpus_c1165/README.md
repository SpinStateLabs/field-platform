# Calibration corpus (SYNTHETIC)

**Everything in this directory is made up.** No line comes from real traffic and none describes a real incident, person,
host or address. The addresses are the RFC 5737 documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`,
`203.0.113.0/24`), the paths are the fictional site of `agent_incident_retro.synth`, the user-agent strings and the three
test tokens are the ones that module already carries, and the only thing added here is the *timing* of the requests. It
does not make the detector's defaults "calibrated" against anything real; see below.

## What it is for (SPEC R-D4)

The retro's thresholds (300 s pivot window, 1800 s session gap, 20 requests / CV 0.35 cadence) are defaults with no
labelled data behind them. This corpus is the first labelled input: each *actor* is one client with a known expected
outcome, and the actors that sit exactly on a threshold come in pairs one step either side of it. So the corpus pins two
things:

1. **What the defaults do** on a labelled set (every actor gets its stated verdict, grade and clause set).
2. **What changing one default changes**: a threshold moved by one step must flip exactly the actor that sits on it. That
   is what a person tuning a threshold for an engagement needs to see, and it fails loudly if the engine's boundary
   moves (`>` against `>=`, a window measured from the wrong request).

## What it is not

* It is **not real calibration**. Thresholds tuned against this corpus would be tuned against our own assumptions. A real
  corpus needs labelled data from a real engagement, and the decision to publish one is Don's (C-1165 does not make it).
* It does not show the detector catches every rogue agent (README, "Declared only").
* The cadence actors carry a payload on purpose: a session with no severe clause is `CLEAR` whatever its timing, so
  cadence only appears on a flagged session (it changes the grade and the clause list, not the verdict).

## Files

* `corpus.py`: the actors (name, client, user agent, request offsets in seconds, expected outcome) and `render()`, which
  turns them into a combined-format log. Deterministic: no clock, no randomness.
* `../test_calibration_corpus_c1165.py`: runs the retro over it.

To add an actor: give it its own address and its own payload variant (two clients sharing a payload form a *campaign* and
gain `S.campaign`), state the expected outcome, and, if it sits on a threshold, add its partner on the other side.
