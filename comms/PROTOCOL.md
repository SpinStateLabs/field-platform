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
