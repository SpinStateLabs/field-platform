VERDICT: FAIL on 1381b5651ff3064951a7587ddd1e4ef3313c377f  (UNVERIFIED: cloud reviewer, no GX10, no docker, CI not read)

C-787, PR 370 (compose conditions from the PR 345/328/353 reviews; C-715). Stacked PR: the head carries 328, 353 and 345 content; the delta under review is the last commit (1381b56 over 5d5cbf7). This SHA only.

OBJECTIONS FIRST
1. The tmpfs exemption added for F-C648-8 is a new bypass of the check it sits in (compose_resolved_check.py, the volume loop: `if opts.get("type") == "tmpfs" or opts.get("device") == "tmpfs": continue`). Probe with check_model on the previous head's file (5d5cbf7) and on this head, same model, top-level volume driver_opts:
   - type tmpfs, device a forbidden system directory: 5d5cbf7 RED, 1381b56 green.
   - type tmpfs, device a forbidden directory, o bind: RED then green.
   - type none, o bind, device tmpfs: RED then green.
   - type none, o bind, device a forbidden directory: RED at both (the ordinary form is still caught).
   The exemption keys on either field alone, and ignores `o`. Docker's local volume driver turns `o=bind` into a bind mount whatever `type` says (training data; MEDIUM; not run, no docker here). So a bind of a forbidden directory spelled with type tmpfs passes the resolved gate. The legitimate case (type tmpfs, device tmpfs, o=size=...) must be allowed; the fix is to exempt only when device is exactly "tmpfs" AND `o` carries no bind flag, or ignore `device` for tmpfs only when `o` has no `bind`. The test (T5 mutant: exemption removed) dies, so the tests pin the exemption but not its limit. Confidence HIGH on the probe, MEDIUM on Docker honouring it.
2. The class is extended, not closed, and the builder note says so: F-C640-1 (variable-held build contexts), F-C640-4 (split defaults, top-level entry keys), F-C640-7 (collides with C-636) and F-C648-6 are named out of scope (builder note 20261105-0100). The static layer still does not catch a defaulted variable that spells a remote context or a split default; I did not re-probe them (out of scope in the PR text). Confidence HIGH that they are open as stated.
3. The resolved layer still reads no value of cap_add, security_opt, cgroup_parent, sysctls, runtime, extra_hosts, host-bound ports, group_add, gpus, deploy devices, build.ssh/secrets/cache_*/network: all green in the probe (a few of them are documented in the docstring; cap_add, security_opt and the others are not listed). The static pins carry these values and refuse `$`, so for repository files the two layers cover them together; a model made from the operator's environment is not covered for them. Stated scope, not a defect; the "not covered" list in the docstring is incomplete. Confidence HIGH.
4. "NOT WIRED into any gate" is now stated in the docstring (F-C648-4 closed by wording). The commit message and card still say "deploy gate" in places; the tool is operator-run. Confidence HIGH.
5. `--profile "*"` is pinned by argv only (T16 dies); behaviour on the pinned compose version is not run (builder says so). Confidence HIGH.
6. A volume `type: BIND` (upper case) is green: compose itself rejects it, so I treat it as not reachable. Confidence MEDIUM.

ASSUMPTIONS
A1 Card scope: each cited condition closed; forms still missed; class closed or extended. A2 The resolved model is what `docker compose config` prints (training data). A3 No docker in this sandbox, none run.

REASONING / CHECKS
- Tests: tools/tests static pins, c512, c638, c715 files: 982 passed.
- Cited findings: F-C640-2 / F-C648-5 (case drift) CLOSED (shared name_problem; mutants T1, T2, T3, T18 killed). F-C648-1 (additional_contexts schemes) CLOSED: every scheme but docker-image:// refused in the probe (https, git, ssh, file, oci-layout, target, service, drive-letter); a `git@host:org/repo` and a bare `github.com/org/repo` are refused as "not absolute". F-C648-2 (dockerfile) CLOSED: relative dockerfile joined to the context, "../../etc/passwd" RED, absolute RED, dockerfile_inline RED (T11, T12, T17 killed). F-C648-3 (profiles) CLOSED for `--run-compose` (T16). F-C648-4 CLOSED by wording. F-C648-7 CLOSED: empty service map raises (exit 3 path); services null, no services, a list also raise. F-C648-8 CLOSED for the legitimate case but with objection 1. F-C640-6 CLOSED for namespaces, privileged, devices, volumes_from (pid, ipc, uts, userns_mode, cgroup, network_mode: host or service forms all RED, case and leading-space variants RED; T6-T10 killed). F-C640-5 non-string handling CLOSED in the static key check and for contexts/dockerfile (T7, T15, T17, T20, T21 killed). F-C640-3: pinned by the new test file (not re-run per survivor). Out of scope by the PR text: F-C640-1, F-C640-4 rest, F-C640-7, F-C648-6.
- Mutants: 21 single-line mutants (name rule x3, empty model, tmpfs exemption, namespace loop and non-string branch, privileged, devices, volumes_from, dockerfile join, dockerfile_inline, scheme refusal, docker-image exemption, non-string context, profile argv, dockerfile non-string, shared-name call, static dockerfile join, static env_file, static crash guard): all 21 KILLED. Each file restored; worktree removed, nothing committed.
- Resolved-layer probe matrix (about 110 forms): contexts and additional_contexts in 24 spellings (remote, scheme, UNC, home, variable, newline, leading space, parent dirs), dockerfile 7 spellings, 25 runtime keys, volumes short and long, named volumes with driver_opts, env_file, secrets, configs: every path-bearing form RED except the tmpfs cases above, `type: image`, tmpfs and npipe volumes (not host paths).
- Commits: 5 in the stack, author and committer Don Hagell no-reply. Diff scan: no estate address, flag value, credential or deploy status.

CONDITIONS
C1 (blocking) Close the tmpfs exemption (objection 1) and pin the three spellings red, with the legitimate tmpfs volume green.
C2 (non-blocking) Complete the docstring's "not covered" list (objection 3) and say whether the two layers or the gate covers operator-environment values for cap_add, security_opt and the rest.
C3 (non-blocking) Reword "deploy gate" in the commit and PR body, or wire the tool.
C4 (non-blocking, carried) F-C640-1, F-C640-4 rest and F-C640-7 stay open until decided.

NOT VERIFIED
GX10 16-suite run, CI by run id, any real `docker compose config` output or `--profile "*"` behaviour, Docker's handling of type tmpfs with o=bind, the static-layer probes for the out-of-scope findings, behaviour on a Windows host.

CONCLUSION
Eleven of the cited findings are closed and well pinned (21 of 21 mutants die). The exemption added for F-C648-8 turns a previously red bind of a forbidden directory green, a regression in the very check this stack exists to harden, so this head fails until C1. The class is extended, not closed. UNVERIFIED.
