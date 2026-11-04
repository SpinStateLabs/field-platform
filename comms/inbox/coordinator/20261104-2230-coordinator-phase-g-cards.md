# Phase G builder cards (coordinator, 2026-11-04)
Source: tasks/todo.md Phase G block as itemised in draft PR 629 (item ids G1..G28 are that file's own).

## B-G19 - C-20, tools half
Narrow the tools' RFC1918 plaintext exemption to loopback when an operator key is present.
Done when: a test shows an operator key is refused on a non-loopback http:// base (RFC1918 included), allowed on https and on loopback http.
Start: git grep -n -i -E "rfc1918|is_private|plaintext" -- tools/ packages/field-core ; read docs/runbooks/v1.2-deploy-rollback.md around line 1101 first. The todo says "no PR; not re-checked against main" (LOW): confirm on current main that the half is still open before changing code, and check open PR titles for it.
Do not arm anything; flags stay off; flags-off behaviour must stay byte-identical.

## NOT assigned (coordinator note, do not claim)
- G23 alert senders and G24 stage controller: Don ruled C-552 "defer all ntfy senders" (docs/runbooks/ntfy-alerts.md). Needs a new ruling from Don before any build.
- G21 (Stage 3 identity gap) and G22 (FIELD_INTERNAL_SECRET, C-54): need a design/roster ruling from Don; the design v0.4 is not in this repo.
- G16, G17, G18, G20, G25, G26, G27, G28: estate work or Don-only go sentences.
