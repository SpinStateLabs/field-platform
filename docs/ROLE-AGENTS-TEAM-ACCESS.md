# ssl-fp role agents: team access and session start (2026-11-04)

Five Managed Agents exist in the `force-field` workspace (`wrkspc_01VufCsY7Hn4WewMsAqFYBRU`), created via the API with a key from `field-platform/tools/key_intake.ps1`. Pattern A needs a self-hosted environment in THIS workspace: `env_01FD7nbGiLfiA4wwj4T3DJjY` belongs to the earlier scope and is NOT verified here. FIELD half provisioned on the GB10 estate (tokens expire 30 days from mint; renew with `tools/renew_token.py`).

| Role | FIELD id | Platform agent id |
|---|---|---|
| red-team | `ssl-fp-red-team` | `agent_01VfLQMGVpqwF6cnoiEX1wbm` |
| architect | `ssl-fp-architect` | `agent_01CFUrUAweLjxSY57cLinFBx` |
| frontdoor-engineer | `ssl-fp-frontdoor-engineer` | `agent_01AthSbHv1rUW7pyVK1TJhVM` |
| router-engineer | `ssl-fp-router-engineer` | `agent_01DykU8ZiA3V3HYC3rp5Spii` |
| runtime-engineer | `ssl-fp-runtime-engineer` | `agent_01Jo57LEGbYFzEBwUrZjFUx9` |

## Who can see and use them

Agents belong to the workspace, not to a person. Any member whose Console **workspace role** allows creating sessions sees them under Agents and can start sessions in environment `GB10` (`env_01FD7nbGiLfiA4wwj4T3DJjY`). Adding members and choosing the role is a Console workspace-members action by an org admin (Don). It is not done by this bundle and the workspace API key used to create the agents cannot do it. The Console role that permits session creation is not in the docs read: check it when adding the first teammate.

## Start a session (teammate, own login or own workspace key; no shared secret in this repo)

```bash
python start_role_session.py red-team rt-<yourname-free-session-name> A
```

Needs `ANTHROPIC_API_KEY` for the shared workspace in your environment. The script creates a session with a $1 budget (edit `--budget-cents`), sends the kickoff, and prints the session id. Session names must be unique among live sessions and must not contain a personal name (they become lock owners in a public repo). Lane: A or B (see the agent prompt).

## Rules for everyone

- Every session is billed to the shared workspace; the budget is a per-session pause, not a daily cap (the FIELD governor cap is the daily authority).
- `push work branch` escalates by design (FIELD verdict ESCALATE). Answer it in the session; never grant it by editing the manifest.
- Archiving a session is permanent; use disposable sessions for tests.
- Placeholders still open: daily cap basis, `always_ask` approver map, GH_TOKEN scope.
