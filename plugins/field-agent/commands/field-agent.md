---
description: Scaffold, bootstrap, and verify FIELD-governed agents built on the field-agent client SDK. /field-agent new to start an agent, verify to run the compliance checklist, bootstrap for operator setup, rest for non-Python agents.
---

# /field-agent — slash command

Handles all `/field-agent *` invocations. Before acting, load the bundled
skill knowledge: `skills/field-agent/SKILL.md` (+ `integration.md` for API
detail, `checklist.md` for verify, `rest-api.md` for rest). Honesty rules
in SKILL.md apply to every output.

## Argument parsing

Strip the leading `/field-agent` and parse what's left:

| Input | Action |
|---|---|
| `` (empty) or `help` | Show usage help below. No mutation. |
| `new <agent-id>` | Scaffold a new governed agent (detail below). |
| `verify [path]` | Run `checklist.md` against the agent source at `path` (default: ask which file). Output the PASS/FAIL block exactly as specified there. No mutation. |
| `bootstrap [agent-id]` | Walk operator setup: manifest → register → cap → policy → mint. Offer a copy of `templates/bootstrap_operator.py` adapted to the agent id, or the equivalent `field`/`governor`/`fieldagent` CLI lines. Make clear this is a HUMAN/operator step. |
| `rest` | Non-Python integration: summarize `rest-api.md` incl. the five fail-closed rules; offer a copy of `templates/rest_api.sh`. |
| `env` | Print the env-var + port table from `integration.md` and note the `log_only` served default and `FIELD_SHARED_SECRET` behavior. |
| anything else | Show usage help. Do not mutate anything. |

## `new <agent-id>` behavior (detail)

1. Copy `templates/agent_template.py` → `./<agent-id>_agent.py`
   (underscores for dashes in the filename). Refuse to overwrite an
   existing file without confirmation.
2. Set `AGENT_ID = "<agent-id>"`; ask for the action names the agent
   performs and set `WORK_ACTION` (and add more governed functions if the
   user lists several actions). Keep the template's exception structure and
   the UTF-8 preamble intact — do not "simplify" the error handling.
3. Manifest: if `./field-manifest.yaml` or `./manifests/<agent-id>.yaml`
   already exists, use it; otherwise copy
   `templates/field-manifest-default.yaml` → `./manifests/<agent-id>.yaml`
   and walk the REPLACE-ME values (principal, org, jurisdiction, kill-switch
   endpoint `http://<killswitch-host>:8005/kill/<agent-id>`, spend cap,
   escalation triggers, delegation granted_by/scope/expiry). Scope entries
   MUST include every action string used in step 2. If the `field` plugin
   (design-time) is installed, `/field validate` is the validator; else
   `field validate` from the monorepo venv.
4. Remind: operator setup must exist before the agent runs — offer
   `/field-agent bootstrap <agent-id>` next.
5. Finish by running `verify` on the scaffold and printing the checklist
   block (it should be COMPLIANT except the E-items, which list the
   operator commands still to run).

## Usage help

```
/field-agent — implement a compliant FIELD-governed agent

Usage:
  /field-agent                     this help
  /field-agent new <agent-id>      scaffold agent + manifest from templates
  /field-agent verify [path]       compliance checklist on agent source
  /field-agent bootstrap [id]      operator setup: register / cap / policy / mint
  /field-agent rest                the three hooks over raw REST (any language)
  /field-agent env                 env vars, ports, estate gotchas

The three hooks: ACTIONS (@governed / check) · USAGE (report_usage, strict)
· LIVENESS (ensure_alive, fail-closed). The SDK is a client, not an
authority — code that never calls it is not governed.
Design-time manifests are the 'field' plugin (/field); this one is the code.
```
