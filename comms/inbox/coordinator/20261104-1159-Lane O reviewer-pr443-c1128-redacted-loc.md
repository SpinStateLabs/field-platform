# Lane O reviewer: PR 443 (C-1128, 422: agent-registry and federation-broker stop repeating a field name; shared redacted_loc helper) @98fc91518769707feaa528e72d6f471123fb8436. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 98fc9151. Lane A/B boundary (field-core, agent-registry, federation-broker). Four commits (ed8b68b1, be07987e, 55e2d43c, 98fc9151), all Don Hagell noreply as author and committer (git log, HIGH). The head does NOT contain current main: 32 commits behind origin/main 97dcfec1. `git merge-tree` of the head onto main: CONFLICT in services/federation-broker/src/federation_broker/api.py and tools/tests/test_422_handler_installed_c1114.py (run, HIGH). I did not write the head. Claimed through dispatch.sh (R-PR443-98fc915). Earlier reports exist (Q-89 verifier note, the groomer note on the two C-1128 PRs 442 and 443); I did not read them; this is independent.

Objections first: (1) PR 443 is the SECOND vehicle of C-1128: PR 442 (head 6385f877) merged as MERGE 19 and main already carries the same fix by another route: agent-registry installs the shared handler (agent_registry/api.py:16 and :158 on main) and federation-broker redacts `loc` with the private `_known_names` import (federation_broker/api.py:19 and :60 on main). What this PR still adds over main is real but small: a PUBLIC `redacted_loc` helper and the extra_forbidden rule for federation-broker (main's federation handler has no extra_forbidden redaction; read, HIGH). (2) federation-broker keeps its own handler on purpose, because its validators write explanatory messages (Don's open ruling C-1123 F3); this PR keeps that and redacts only `loc` (read, HIGH). (3) a caller-supplied field name that equals a KNOWN field name stays visible by design (the helper's docstring: "A key that happens to equal a field name stays").

Run here (cloud, scratch worktree on 98fc9151, relative PYTHONPATH of every service src and packages src plus the two services' tests directories): field-core test_http_errors_redacted_loc_c1128.py plus tools/tests/test_422_handler_installed_c1114.py 46 passed; agent-registry and federation-broker test_422_no_echo_*_c1114.py 6 and 8 passed. NOT run: the 16-suite set, CI.

Mutants (20 written; 1 did not apply and is excluded; 19 run in a scratch worktree on http_errors.py, federation-broker api.py and agent-registry api.py; each against the PR's four test files, survivors against the whole field-core suite. My first sweep did not run the older field-core tests for survivors, so it overstated survivors: I re-ran, and one mutant I had thought a gap (dropping the caller-key redaction) is killed by an older field-core test; the table is the corrected run):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 redacted_loc replaces a caller-chosen string in loc (one more did not apply) | 4 | 3 | 1 |
| B2 the last part of an extra_forbidden error is replaced | 4 | 3 | 1 |
| B3 the shared handler uses redacted_loc | 3 | 2 | 1 |
| B4 federation-broker keeps its messages, drops input and redacts loc | 4 | 3 | 1 |
| B5 agent-registry installs the shared handler | 4 | 3 | 1 |
| Total (counted from the rows) | 19 | 14 | 5 |

Survivors (5): 1 equivalent (an unused extra import), 4 real LOW pin gaps:
- F-O-pr443-1: the extra_forbidden last-part redaction can be removed from redacted_loc with the WHOLE field-core suite and the PR's tests still green (the same hole as my MERGE 18 finding F-O-m18-1): no test builds an unexpected field named like a known field. Because the same rule is passed to federation-broker only through this helper, the PR's headline addition has no test (http_errors.py redacted_loc).
- F-O-pr443-2: the shared handler can pass `redacted_loc` a dict WITHOUT the error type (so the extra_forbidden rule never fires) and nothing fails (same root as -1, via handler).
- F-O-pr443-3 (MEDIUM-LOW): federation-broker can pass an EMPTY error to the helper, so `loc` becomes `[]` for every error (the field name lost), and its test still passes: the test checks that the marker is absent, not that the field name is kept (federation_broker/api.py, the errors line).
- F-O-pr443-4: the known-name set can gain an extra name ("zz") unnoticed (the known set is not pinned exactly).

CONDITIONS (blocking): C1 the coordinator's decision between PR 442's landed form and this one (rebuild on 97dcfec1 resolving the two conflicts, or close as superseded and take only `redacted_loc` plus the extra_forbidden rule in a new PR); I make no merge call. C2 if this lands, CI green and a GX10 16-suite run on the exact rebuilt head (I could not run it).
Optional, NEW PR after the head is frozen: F-O-pr443-1..4 pins (an unexpected field named like a known field; an assertion that federation-broker keeps `loc` non-empty).

Tokens/cost line: not available to me. I do not know.
