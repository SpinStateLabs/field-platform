VERDICT: PASS WITH CONDITIONS on d4902a0fff7c49bd36943d82249aeb6acfba1d13 (PR 387); PR 385 @ 112cf16d3328fc431c106d75f8e6d834a8ee2ef6 is an ancestor of it and carries the same verdict
Card C-905. Cloud reviewer, no GX10, no docker, CI not read: UNVERIFIED until re-run.

OBJECTIONS FIRST
1. The card calls 387 and 385 "two follow-ups" with overlap to resolve. They are not two parallel PRs: they are one linear stack. 345 (2 commits) < 353 (+2) < 370 (+1) < 385 (+2) < 387 (+1); each is an ancestor of the next (`git merge-base --is-ancestor`, HIGH). PR 387 over 385 adds 83 lines in two TEST files only; no tool code (git diff 385..387).
2. The class is still open in the resolved layer (F-C905-1): a non-mapping ENTRY under a top-level section, or a malformed service volume entry, reads clean (exit 0). The C-817 fix covers the static layer only.
3. The resolved tool is still not wired into any gate (its own header, C-715), so every refusal below depends on an operator running it.
4. Failure conditions: (a) a model produced by something other than `docker compose config` (file or stdin) with an odd shape passes as clean; (b) a tmpfs-typed named volume skips the device check on the strength of a string match that nothing here proves Docker honours; (c) merge in the wrong order is harmless for the stack but closing the stacked PRs separately would lose commits if 387 is not the one merged.
Steelman: compose itself rejects every malformed shape below at load, so the second net only matters for hand-made models, which the tool says it reads as data.

ASSUMPTIONS
A1 Heads as named, fetched this session. A2 Linux only. A3 `docker compose config` output is well-formed; the tool also accepts files/stdin.

REASONING
1. Overlap and merge order. 387 vs origin/main, 345, 353, 370, 383, 375: `git merge-tree --write-tree` exit 0 for each; 385 likewise; 345/353, 353/370, 345/370 also exit 0. Merge 387 alone: it contains all of 345, 353, 370, 385; earlier PRs then show as merged. Merging in order 345, 353, 370, 385, 387 is also clean. Old PRs 345, 353, 370, 385 can close once 387 lands. HIGH.
2. Conditions closed. Tests at 387: six compose test files 1045 passed (HIGH). 345-side: C-765 F-C765-1 (non-string carriers) closed at static and, for service-level, resolved layers; top-level device, secret file, config file closed in the static layer by 387 (tools/tests/test_compose_static_pins.py new block, M1-M3 below). 353-side C-735 F-1 (root behind symlink), F-2 (non-string), F-3 (`..` after a link), C-698 F-1..3 (UnicodeDecodeError, non-mapping, empty services): closed in code (tools/compose_resolved_check.py:150-170, 105-125) and probed. C-648 F-1/-2 (scheme and dockerfile contexts) refused (probe, M9, M10). Still open from earlier lists: C-648 F-8 turned into the tmpfs exemption (line 171-172); C-640 F-1/F-4 (static: variable-held remote context, split-default caller-key path) not re-probed by me (not verified); sibling-import failure for a lone copy (Lane 4 F-C387-1, not re-probed).
3. Probe of check_model on 34 forms (scratch, throwaway paths, no real data): refused: /etc, short syntax, relative, top-level device bind, network_mode host and bridge, privileged "true", pid host, userns HOST, git-URL context, additional context /etc, env_file, secret and config file, NUL, `//etc`, `..` climb, `.GIT`, `.env.local`, fullwidth slash, /proc/self/root. Clean: `type: BIND` upper-case and `" bind"` (type match is exact, line 187), `extends` key, `cap_add SYS_ADMIN` (stated limit), build context equal to the repo root (documented), tmpfs-typed named volume with a host device. HIGH for the results; whether Docker would accept the upper-case type is not verified.
4. CLI exit contract on odd shapes (`python -I`, no traceback in any): exit 3 for top-level `volumes`/`secrets`/`configs` that are lists or strings, services list, bad additional_contexts. Exit 0 (clean, should be 3 or 2 by the docstring's "never read as clean") for: a top-level volume whose value is a string; a volume whose driver_opts is a list; a secret whose value is a list; a service volume entry that is a list or an integer; a volume entry whose type is a list. HIGH (observed). This is F-C905-1.
5. Mutants (10, each one edit, tests run `-x`, restored by git checkout, worktree clean after): M1 static top-level device non-string check off, M2 secret/config file check off, M3 unknown-shape except narrowed, M4 `must_be_text` off on the service volume branch, M5 tmpfs-device exemption removed, M6 allowed roots not resolved under realpath, M7 original string not resolved, M8 empty service map allowed, M9 additional_contexts scheme refusal off, M10 dockerfile join with context off: ALL 10 KILLED. HIGH.
6. Authorship: all commits Don Hagell no-reply (author and committer). No estate address or flag value seen in the diffs I read.

FINDINGS
F-C905-1 (MEDIUM-LOW, no block for merge; blocks any "second net is total" claim): resolved layer reads malformed entries as clean: tools/compose_resolved_check.py:166-174 (top-level entries), :184-190 (service volume entries). Raise ValueError (exit 3) like the neighbouring cases and pin each.
F-C905-2 (LOW): type match exact: `type: BIND` or padded reads as no bind (line 187); the static layer refuses upper-case. Align them.
F-C905-3 (LOW-MEDIUM): tmpfs exemption (line 171-172) is a string match; unproven against Docker. Narrow to type tmpfs with no `o: bind`, or cite the Docker behaviour.
F-C905-4 (LOW): tool unwired (carried).
F-C905-5 (INFO): PR 387's own claim that it closes more than C-765 F-C765-1 does not hold; Lane 15's C-900 point stands.

CONDITIONS
C1 (non-blocking) F-C905-1. C2 (non-blocking) F-C905-2 and -3. C3: merge 387 as the one PR, then close 345, 353, 370, 385 (blocking only for hygiene: merging an earlier PR alone leaves the rest open).

NOT VERIFIED: GX10, CI, Windows junctions, C-640 F-1/F-4 at this head, lone-copy import, Docker behaviour for tmpfs-typed volumes.

CONCLUSION
The two "follow-ups" are the top of one clean linear stack; merge 387 and close the rest. It closes the conditions listed in REASONING 2 and survives 10 of 10 mutants; the class is not closed: malformed entries and two exact-match rules in the resolved layer remain.
