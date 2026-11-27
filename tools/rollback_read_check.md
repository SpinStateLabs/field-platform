# Rollback-read check

`tools/rollback_read_check.py` answers one question before a deploy: **if we roll back, can the old release still read the ledger the new release wrote?**

It finds every ledger event type added between two commits, writes a throwaway ledger holding them with the **new** code, and runs the **old** code's readers on a copy. The check also covers event types whose payload shape changes: list each in `CHANGED` with a payload in the new shape, and it is written and read on every run.

It contacts no estate. Child processes get a scrubbed environment, upstreams are in-process stubs, and all files live in a temporary directory that is removed afterwards.

## Run it (GX10, train operator)

From a field-platform checkout, with the interpreter that has the services' dependencies:

```bash
git fetch origin main
python3 tools/rollback_read_check.py --repo . --old "$OLD_SHA" --new origin/main --python "$TRAIN_PYTHON" --json rollback-read.json
```

`--old` is required and has no default: give the SHA of the release a rollback would return to. A run without it exits 2.

Pass the exact deploy SHA as `--new` for the final run. `$TRAIN_PYTHON` stands for the train's virtual environment interpreter.

## What PASS looks like

The last line is `RESULT: PASS (...)` and the exit code is 0. That means:

- every added event type has a fixture;
- each reader answered `OK` or `SKIPPED` for each type;
- the old release booted on the ledger, verified it, served `/health`, `/events` and `/retention/check`, and appended one more event with the chain still intact.

| Exit | Line | Meaning |
|---|---|---|
| 0 | `RESULT: PASS` | Safe to read after a rollback, for what this tool covers |
| 1 | `RESULT: FAIL` | A reader refused or crashed, or a new type has no fixture. The failures are listed |
| 2 | `RESULT: ERROR` | The check itself could not run. This is **not** a pass |

## Readers, per event type

| Reader | What it runs at the old commit |
|---|---|
| `parse` | `LedgerEvent` validation |
| `ledger_filter` | sealed-ledger `GET /events?event_type=` |
| `replay` | incident-replay summary, replay and Markdown. `SKIPPED` for an event with no `agent_id`, which an agent replay does not show |
| `ops_console` | ops-console `/api/events` and CSV export |
| `status_pairing` | `estate_probe.check_status_pairing`: a new `kill.*` type must not count as the kill behind a registry status change |
| `attest` | the attestation pack build, and the metrics that query the type |
| `ops_overview` | ops-console `/api/overview` recent events |

Whole-ledger readers also build the attestation pack, run and render a lifecycle sweep, and read the console overview's ledger sections.

After the table the tool prints, for each row and reader, **the line the old release shows** (the rows are synthetic). Read these: a reader can answer `OK` and still show less than before. A reader that requires a key the new shape dropped answers `CRASH`, which fails the run.

## What it does not cover

- It uses synthetic events, not a copy of a live ledger.
- It finds new event **types** by itself. A changed payload on an existing type is exercised only when it is listed in `CHANGED`.
- Event types are found by scanning dotted string literals. An event type built entirely at run time would be missed.
- Rotated segments, archives and signed export bundles are not exercised.
