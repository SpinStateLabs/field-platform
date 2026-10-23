# deployment_agent - SKELETON (ADR-0079)

Status: skeleton. Design source: harness repo `adr/ADR-0079-*.md` (branch `rebaseline-2026-10`) and
`docs/proposals/03-autonomous-cicd-and-key-management.md`. Accepting the ADR authorised this skeleton, not an
install: nothing here mints, rotates, deploys or contacts anything. Standard library + PyYAML only; no network
call anywhere (a test greps the package's imports for network and subprocess libraries).

## What exists

| Piece | File | ADR |
|---|---|---|
| Refuse list as code: `refuse(action) -> reason or None` over a typed `Action`; rules R01-R15 | `refuse.py`, `actions.py` | s5, s3 |
| Rotate-then-verify-then-revoke state machine: explicit transition table (planned, minted, installed, verified, old_revoked, done, rolled_back, halted) | `states.py` | s6 |
| Crash-resumable engine: lock, append-only journal, atomic install with byte-identical backup, negative-control verifier check, restore on failed verification, never undo a human revocation | `rotation.py`, `journal.py` | s6 |
| `Provider` protocol, an in-memory `FakeProvider`, and `RealProviderNotImplemented` (raises `NotImplementedError` pointing at the ADR) | `provider.py` | s6, s9 |
| Release-record verifier skeleton (exact 40-hex SHA, signature via an injected verifier) | `release.py` | s4.6 |
| CLI `python -m deployment_agent plan` / `run --dry-run` | `cli.py` | - |
| Manifest sketch | `../../manifests/deployment-agent.yaml` | s3 |

Run from `tools/`: `python -m deployment_agent plan --target fly-app-a` and
`python -m deployment_agent run --target fly-app-a` (the default is a dry run: a SIMULATION against the fake
provider). `run --no-dry-run` is refused unless `--manifest` names an existing file AND `--i-have-a-provider` is
given, and is then refused anyway: no real provider exists.

## What is NOT built

- Real providers (Fly, GitHub environment secrets, GB10 adapters): `RealProviderNotImplemented` only.
- Signature cryptography and key handling: the release verifier takes an injected `SignatureVerifier`; the default
  refuses everything. GitHub attestation's feature set is unverified (ADR).
- Rollout, systemd/cron, the sha256 pin check, the Unix user, the estate-kill watcher, spend metering calls, ledger
  appends, the daily digest, the model-key rotation, and the deploy / canary / post-deploy / rollback-of-images
  steps (only their ACTION KINDS and refuse rules exist). ADR-0079 s9 says none of the s2 scope is built before the
  prerequisites (i) CI `permissions:` and SHA-pinned actions, (iv) a ledger caller key, (vi) the kill watcher and
  (vii) harness CI.
- `rotate()` does not decide whether a rotation is due (cadence is a placeholder); a scheduler would.
- A human-approval record verifier: `Action.human_approval` is an id that a later change must check.
- A halt-clearing UI: `Rotator.clear_halt` exists and records a named human reference; nothing calls it.

## Where a credential value is written

Never in the journal (a closed field list, a secret-shape guard, a literal check against every minted value; a
violation raises and writes nothing). During a rotation the value exists in memory as `SecretValue` (repr/str/format
print `<redacted>`) and in two 0600 files under `<state>/stage/`: `<target>.new` (between the mint and the end of the
run) and `<target>.old` (byte-identical backup of the consumer's old value, needed for the restore). Both are deleted
when the run ends (`done` or `rolled_back`); a `halted` run keeps them as the human's recovery material. Ids are short
opaque handles; the journal never holds a token id longer than 23 characters or a 40-hex SHA outside the `sha` field.

## Refuse list mapping

R01-R12 are the numbered items of ADR-0079 s5, in order. R13 (revoke the old credential only after its replacement
is verified), R14 (a scope wider than the ADR ceiling: the agent cannot widen its own scope) and R15 (an action
outside the manifest scope) come from the build instruction and s3/s6. Touching an estate shared secret in any way is
R03. Every rule has cases that must be refused BY THAT RULE and a mutant check (a scratch copy of the package with that
rule deleted from `RULES` must make a case go red): `tools/tests/test_deployment_agent_refuse.py`.

## Manifest sketch

`manifests/deployment-agent.yaml`: least-privilege `delegation.scope` (exactly the six ADR scopes; the five
deliberately-absent ones are not listed), spend cap with `on_breach: halt`, estate kill endpoint plus
`kill_switch.local_sentinel` and `sentinel_max_age_s`, `granted_by` Don Hagell, expiry within 30 days, deny patterns
for prune / apps destroy / volume delete / git push. NOT installed, no roster row, no token.

Placeholders (Don's): `spend_cap.limit` (schema needs a number > 0; `1` is a stand-in), `sentinel_max_age_s` (`300`,
must exceed twice the watcher poll plus its timeout), `delegation.expiry` (`2026-11-22` = ADR date + 30 days), the
rotation expiry (30 days is the ADR's proposal), rotation cadence, model-key cadence. The ADR states no other figure.
`model_provider` is a descriptive string because the schema requires the field and the ADR says "none".

Validation, offline (no network), from the repo root with this checkout on `PYTHONPATH`:

    python -m field_core.cli validate manifests/deployment-agent.yaml

Result when this was written: `Status: VALID_WITH_WARNINGS`, no critical gaps, one warning
(`delegation.expiry ... is near-term (within 30 days)`, inherent in a 30-day TTL). Run it on the venv whose editable
installs may point at ANOTHER checkout: confirm with `python -c "import field_core; print(field_core.__file__)"`.
The test `test_the_manifest_validates_with_field_core_offline` runs the same validator in-process.

## DOA roster (nothing was edited)

The generator needs NO new grantor row: the manifest's `granted_by` is the existing "Don Hagell, Spin State Labs",
so the existing row's `allowed_scope` would WIDEN by the six scopes (`test_the_roster_generator_needs_no_new_grantor_row_only_a_wider_existing_one`
runs the generator on copies in a scratch directory). Consequences for whoever installs this, all Don-approved changes
with a printed diff first (ADR s3): (1) that row's `max_spend_usd` is not set by the generator and any hand-set value is
overwritten on regeneration; (2) the registry record's `manifest_ref` must use the FILE name `deployment-agent.yaml`
(the agent id is `ssl-deployment-agent`; the resolver matches by file name); (3) the manifest must be copied to the
estate before arming the roster (manifests/README.md). Widening the shared grantor row grants the existing ssl agents
nothing (each token is still bounded by its own agent's manifest, D.scope), but it is the row's envelope, so decide
whether the deployment agent should have a separate grantor string instead. That is a human decision recorded here, not made.

## Tests

`tools/tests/test_deployment_agent_*.py` (run by the existing CI step `pytest -q tools/tests`; `.github` untouched):
refuse list and mutants, state machine and failure injection (a simulated crash at every named point between every pair of
states, with resume, and a second crash during the resume at every point), release verifier, CLI and manifest.

## Orphans, stamps and halts

Every credential the agent mints carries a stamp (`da-<run id>`) in the provider's name/label/metadata field
(`Provider.mint(target, ttl_days, label)`; `describe()` must return it). A resumed run sweeps ONLY credentials
carrying its own run's stamp. A credential that is neither in the pre-mint snapshot nor stamped by this run (a human
or another tool minted it) is never revoked: it is journaled by id and the run HALTS. An orphan of its own that
cannot be revoked (the provider raises, or does not confirm) also halts the run, its id stays in the journal, and the
halt blocks every later run for that target until a named human clears it. Provider exceptions are reduced to
`ProviderError("provider <method> failed: <ExceptionType>")`; the provider's message text is never propagated or
journaled.

## Known gaps before a real provider exists

Left open on purpose (independent review of PR 21), to be closed before any real provider is wired in:

- Journal tamper-evidence (review row 3): the journal is append-only by convention and by the engine, not hash-chained
  or signed; someone with the same Unix user can edit it.
- A verifier for the human-approval record (review row 12): `Action.human_approval` is a non-blank string the caller
  asserts; nothing checks that a separate approver signed it. With one owner this is a speed bump either way (ADR s8).
- Review rows 13 and 14: their text was not in the brief I worked from, so they are recorded here as "open, to be
  filled in from the review" rather than guessed.
- Carried from the first version: signature cryptography, real adapters, rollout, spend metering, ledger appends, the
  kill watcher, and a cadence decision (see "What is NOT built").
- The stamp relies on the provider returning the label; a provider that cannot store one cannot be used with the sweep
  (the engine treats a minted credential without the stamp as a mismatch and rolls it back).
