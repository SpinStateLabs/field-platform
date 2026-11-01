# Standing instruction to all lanes: never idle, poll the queue every 5 minutes

From the coordinator, on Don's instruction (2026-10-31).

1. Poll every 5 minutes (loop or scheduled check): `git fetch origin comms`, read `comms/TASK-QUEUE.md`, then `comms/BACKLOG.md`. Take the lowest OPEN card for your role that no lock or CLAIMED line covers and that does not wait on a PR or a Don ruling. Claim it by your usual claim line, work it, report in `inbox/coordinator/`.
2. Do not stop because the queue looks empty. Open-card counts in the queue file are often stale (a card can be answered while its line still says OPEN): check `inbox/coordinator/` for a report naming the card before you skip it, and check that the PR head you are asked to review is still current (`gh pr view <n> --json headRefOid`).
3. The coordinator restocks the queue every 5 minutes while lanes are idle. If you find nothing for your role after a full poll, write ONE line in `inbox/coordinator/` ("lane <n> idle: <reason>") and keep polling; do not repeat it each tick.
4. Rules unchanged: author never reviews own work; one card = one branch; no force-push; commit identity must be the repository noreply identity for author and committer; public repo, so no estate values and no exploit recipes; no merge, deploy or secrets from a lane.
5. Roles (Don, 2026-10-31): builders Lanes 1, 11, 12, 13; reviewers Lanes 7, 14, 15 (14 and 15 are cloud, read-only, output UNVERIFIED unless re-run).
