# Calibration corpus (synthetic)

**This corpus is synthetic. It contains no real traffic and no real incident data.** Every address is an RFC 5737
documentation address (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`), every host and user agent is fictional or
the fictional ones the demo log already uses, and every payload is one of the short canonical web-security test strings
in `agent_incident_retro/synth.py`. Nothing here came from an estate, a customer or an incident.

SPEC R-D4 says the retro's thresholds (300 s pivot window, 1800 s session gap, 20 requests at a coefficient of
variation of 0.35) are defaults, not calibrated, because no labelled corpus exists. This is the first one: 15 made-up
actors (103 log lines) whose ground truth is set by how the scenario is built, in `labels.json`:

| truth | actors | what they do |
|---|---|---|
| benign | 6 | three people browsing (one mistypes three addresses), a monitoring client polling at a fixed cadence, a person whose search words look like query keywords, an archive crawler |
| authorized | 1 | a scanner the owner authorised (hostile requests, allowed by address) |
| rogue | 8 | a fast pivot, a slow pivot (430 s), a probe-only client, a payload under a spoofed assistant marker, a low-and-slow actor (one payload every two hours), and one payload replayed from three rotated addresses |

Files: `calibration.log` (NCSA combined format, read with `retro scan --format clf`), `labels.json` (truth and a
scenario sentence per address), `make_calibration_corpus.py` (the generator: deterministic, no random numbers; the
committed files are exactly what it writes, which `tests/test_calibration_corpus_c1165.py` checks).

## What it shows at v0.1.1 (counts, pinned by the test)

- At the default thresholds no benign actor is flagged and all 8 rogue actors are flagged at REVIEW or above.
- Only 1 of the 8 rogue actors (the fast pivot) is ESCALATE; the authorised scanner is ESCALATE until its address is
  listed, then AUTHORIZED, and is reported either way.
- The slow pivot (430 s) is REVIEW at the 300 s default window and ESCALATE at 900 s; widening the window flags no
  benign actor in this corpus.
- The low-and-slow actor is five REVIEW findings at the 1800 s session gap and one at a gap above two hours.
- A fixed-cadence poller raises no finding on its own.

## What it does not show

Nineteen sessions are far too few to set a threshold: the corpus makes the question measurable, it does not answer it.
Every result is for made-up scenarios chosen by the author, so a rate computed from it says nothing about real
traffic. A corpus of real, labelled incidents is a separate piece of work, and whether any such data may be used or
published is the owner's decision, not this file's.

Regenerate with `python corpus/make_calibration_corpus.py` from this package's directory.
