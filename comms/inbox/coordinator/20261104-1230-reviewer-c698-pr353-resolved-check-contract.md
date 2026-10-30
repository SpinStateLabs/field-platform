VERDICT: PASS WITH CONDITIONS on 783a85fa9d32818ead55853bc20cda41d77142c2 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the two resolved-check test files ran: 126 passed)

Head matches the card. PR 353 is a STACK: three commits on main, 7679259 and f3787c9 (the bind-source work reviewed under other cards) then 783a85f (the C-638 change this card is about). Author and committer of all three are the no-reply identity. This report covers 783a85f and the whole of tools/compose_resolved_check.py at that head; the two earlier commits were not re-reviewed.

OBJECTIONS FIRST
1. The exit contract (0 clean, 2 a source is refused, 3 the tool could not do its job, "never 1") is broken by one input: a model file that is not valid UTF-8 ends in a traceback with exit code 1 (the file is read with open().read() at compose_resolved_check.py ~line 190; UnicodeDecodeError is not in the caught list OSError, RuntimeError, YAMLError, SubprocessError). PROVEN. The card asked for the 0/1/2 separation; the tool's own contract is 0/2/3, and exit 1 is exactly the value it says it never uses.
2. A model that is empty, blank, a list, or any non-mapping answers "REFUSED the model has no services" and exit 2 (check_model returns that text as a problem). The docstring says a model whose shape the tool does not know is exit 3. So "refused" (2) and "could not do the job" (3) are confused for the shapes most likely to come from a failed pipeline (empty stdin). PROVEN. LOW-MEDIUM.
3. A model with an empty services mapping, {"services": {}}, prints "every bind source is allowed" and exits 0: a pass over nothing. A deploy gate that treats 0 as green would pass a truncated model. PROVEN. MEDIUM-LOW.
4. A relative --repo-root without --realpath is normalised to "/" (normal(".") returns "/"), so in-repo sources are refused as "outside the repository". Fail closed, misleading text. PROVEN. LOW.
5. Without --realpath a symlinked source is judged by its spelling, so a link to a denied tree passes (documented: "judged by its spelling"). Probe: a link into a system tree: exit 0 without --realpath, exit 2 with it. As designed; the deploy gate must pass --realpath.
6. Documented unread keys (devices, build.dockerfile and others) pass silently: a model with a device mapping of a host memory device exits 0. Documented, and covered by the static pins' key allowlist for repository files only.

ASSUMPTIONS
A1 "The root resolves outside the repo" is tested with a repo root reached through a symlink and --realpath. A2 Probes ran on this tool as a command line with model files in a scratch directory; no docker. A3 One interpreter, Linux.

REASONING
1. Probe table (exit code; reason): no arguments 3 (usage); unknown flag 3; missing --repo-root 3; --help 0; non-UTF-8 file 1 (traceback); {} 2; blank file 2; list 2; {"services": {}} 0; a 5000-deep nested list 3 (RecursionError caught at the read stage); services.a.volumes as a string 3 (unknown shape, no traceback); bind of a system tree 2; bind inside the repo 0; short-syntax "/etc:/c" 2; build.context of a system tree 2; additional_contexts with a path 2 (a scheme URL is deliberately not judged); devices mapping 0 (documented); symlink to a system tree: 0 without --realpath, 2 with; repo root via a symlink with --realpath: accepted. HIGH.
2. Mutants (each applied alone to the tool, restored; worktree removed; nothing committed): narrow the catch-all to ValueError -> 7 failed; repo root not realpathed -> 1 failed; usage error exits 2 -> 4 failed; read error exits 1 -> 4 failed; unknown shape exits 1 -> 11 failed; realpath ignored -> 3 failed; refused exits 1 -> 5 failed; additional_contexts not judged -> 1 failed. A ninth mutant (env_file not judged) was interrupted by me and its result is not available; I do not claim it. HIGH for the eight.
3. Root and realpath: the root is resolved under --realpath (compose_resolved_check.py near the main() tail), which is the PR's F-C585-1 fix; a checkout reached through a link is judged correctly. HIGH.
4. Diff scan of the head: no estate address, SHA, flag value, deploy status or credential; paths are repository-relative or made up. HIGH.
5. Commit 783a85f carries a "Co-Authored-By" trailer naming an assistant at a no-reply address; this passes the identity guard of PR 346 (it checks the four identity fields only).

CONCLUSION
PASS WITH CONDITIONS. The C-638 changes work as claimed and their tests are red under eight mutants. The exit contract is not fully kept (non-UTF-8 input gives exit 1; empty or non-mapping input gives 2 instead of 3), and an empty-services model is a green. Conditions, none blocking:
- C1 F-C698-1/-2: catch UnicodeDecodeError (and any read error) as exit 3; make a non-mapping model exit 3.
- C2 F-C698-3: fail with exit 3 (or print a warning) when the model has zero services.
- C3 F-C698-4: require an absolute --repo-root.
- C4 (decision): the deploy runbook should call the tool with --realpath and from the host named in the model; confirm.

FINDINGS
F-C698-1 MEDIUM-LOW, tools/compose_resolved_check.py (main(): the read of the model file; except tuple lacks UnicodeDecodeError): traceback and exit 1. PROVEN.
F-C698-2 LOW-MEDIUM, compose_resolved_check.py check_model() first return (non-mapping or no "services" mapping reported as a refused source, exit 2). PROVEN.
F-C698-3 MEDIUM-LOW, compose_resolved_check.py check_model()/main() (empty services passes with exit 0 and the message "every bind source is allowed"). PROVEN.
F-C698-4 LOW, compose_resolved_check.py normal() and main() (relative --repo-root becomes "/"). PROVEN.
F-C698-5 INFO, tools/compose_resolved_check.py docstring (unread keys; devices etc.) accurate. HIGH.

NOT VERIFIED: the two earlier commits of the stack; behaviour against a real `docker compose config` output (no docker here); CI; the env_file mutant; Windows paths.
