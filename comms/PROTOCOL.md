# comms PROTOCOL (field-platform)

Branch `comms` (orphan). Fast-forward only: on a rejected push, fetch, rebase, retry. Never force-push.
Integration branch: `main`. Coordinator (one session, ruled by Don 2026-10-28) is the ONLY writer of STATUS and the only session that merges, deploys, rotates secrets, touches production or runs the live gate.

- `TASK-QUEUE.md`: cards `C-<n>`; check origin first so numbers do not collide. States: OPEN, TAKEN <role>, REVIEW, DONE.
- `inbox/<role>/`: one file per message `YYYYMMDD-HHMM-<from>-<slug>.md`. Roles: coordinator, builder, reviewer.
- Author never reviews own work. A merge needs an independent reviewer PASS and a green GX10 run on the EXACT head, rebased on current `main`.
- Cloud sessions without the GX10 produce UNVERIFIED branches until the coordinator re-runs them.
- Findings carry file:line, HIGH/MEDIUM/LOW. Unknown means "I do not know". Never print a secret.
- Do not modify SpinStateLabs/Force-Field or force-field-agentic-harness; note their coordinator in that repo's comms/inbox/coordinator/.

- Cards: only the coordinator edits TASK-QUEUE.md and assigns numbers. A teammate who wants a card proposes it in inbox/coordinator/ (title, role, files, done-when); the coordinator numbers and queues it. (2026-10-28, after Don noted teammates pushing their own cards.)

- Idle teammates (Don, 2026-10-28): never stop for lack of work. With no OPEN card, claim the lowest UNCLAIMED item for your role in comms/BACKLOG.md (one commit editing that line), work it, report in inbox/coordinator/. The coordinator keeps BACKLOG.md stocked and promotes claimed items into TASK-QUEUE cards.

- Lanes (coordinator, 2026-10-29; builders claim by messaging the coordinator, take the lowest OPEN card in their lane, never edit TASK-QUEUE.md; a lane card needs no extra claim step beyond the message):
  - Lane 1 (tools, field-core, console): C-4, C-191, C-184, C-30, C-73, C-105, C-122, C-127, C-47.
  - Lane 2 (service tests): C-137, C-153, C-162, C-163, C-168, C-179, C-198, C-145, C-148, C-159, C-128.
  - Lane 3 (docs, runbooks, CI, compose): C-188, C-199, C-176, C-164, C-129, C-147, C-149, C-151, C-152.
  - HOLD (waiting for Don, do not start): C-169 (D-23 ruled, ok to start), C-180 (D-24 provisional), C-192 (D-26 provisional), C-189 (needs Don's OK for live reads).
  - Reviewer lanes: A = tools, field-core, sealed-ledger, force-gateway; B = registry, approver, sentinel, ops-console, delegation, spend, kill, lifecycle, federation, incident-replay, attestation, crosswalk, docs.
- GX10: a local session can fetch any pushed head straight from GitHub (`git fetch https://github.com/SpinStateLabs/field-platform.git refs/heads/<branch>:refs/heads/<name>`), then `git worktree add ~/ff-work/wt-<name> <name>` and `setsid nohup ~/ff-work/runbatch.sh <name>`; marker ~/ff-work/<name>-all.done, log ~/ff-work/<name>-all.log. At most one full run per session at a time.
- Python path rule: run tests with RELATIVE PYTHONPATH (`PYTHONPATH='../../packages/field-core/src;src'` from a service dir); a `$(pwd)` list is not path-converted by Git Bash and Python silently imports the main-checkout copy. Check `hasattr` on a new symbol.
