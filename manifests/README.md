# manifests/ — REAL FIELD manifests (Spin State's own agents)

Not demo data. `integration/demo/manifests/` holds the synthetic scenario;
this directory holds the manifests of the agents Spin State Labs actually runs
(dogfood estate = GB10, sentinel **enforce**).

| Manifest | Agent | Skill |
|---|---|---|
| `ssl-timekeeping-agent.yaml` | daily timesheet drafting + client portal entry | `agents/ssl-timekeeping-agent/SKILL.md` |
| `ssl-invoicing-agent.yaml` | client invoicing + Zoho Books | `agents/ssl-invoicing-agent/SKILL.md` |

## Where the sentinel reads them

The conformance-sentinel resolves each registered agent's `manifest_ref` on
**its own filesystem** — inside the compose stack that is the `field-data`
volume, mounted at `/data`. `tools/provision_ssl_agents.py` registers
`manifest_ref: /data/manifests/<agent>.yaml`; the files must therefore be
copied into the volume after every change, or every `/check` for that agent is
an `I.manifest` BLOCK (enforce) — all authority lost, by design.

On the GB10 (from `~/field-platform`, after `git pull`):

```bash
docker run --rm -v field-platform_field-data:/data -v "$PWD/manifests:/src:ro" \
  alpine sh -c 'mkdir -p /data/manifests && cp /src/ssl-*.yaml /data/manifests/ && ls -l /data/manifests'
```

No container restart is needed — the sentinel re-reads a manifest when its
mtime changes (mtime-cached validation).

## Action strings are load-bearing

`delegation.scope` entries are matched verbatim against the token scope and the
`-Action` strings in the skills. Change one, change all three:
manifest → `tools/provision_ssl_agents.py` (re-mint) → `agents/<id>/SKILL.md`.

Deliberately absent from scope (so any attempt is `D.scope` BLOCK):
timekeeping `submit for approval`; invoicing `send invoice email`,
`mark invoice sent`, `apply payment`.

## Validate

```
field validate manifests/ssl-timekeeping-agent.yaml
field validate manifests/ssl-invoicing-agent.yaml
```
