# wave2-engineer: reviewer width 2, not 6 (question, with the default I am acting on)

What I need: a yes before going above 2 parallel reviewer subagents.
Why: Projects/CLAUDE.md directive r1 item 2 asks for a cost-optimizer pre-flight estimate before any fan-out of
more than 2 agents. GO-LIVE-LOOP.md sets reviewer WIDTH 6. The stricter rule wins (r1 item 7), and I have no
pre-flight estimate.
Options:
  (a) width 2 (the default I am acting on now);
  (b) width 6 once you (or cost-optimizer) give an estimate;
  (c) a width you name.
Recommended: (a) until you answer.
Meanwhile: R-PR1091-b974fa2 and R-PR1090-3e950b3 are claimed and in review (2 Opus subagents).
Rough cost (REASONED from my earlier reviews in this session: about 200k subagent tokens per full review): about 200k
Opus tokens per card.
