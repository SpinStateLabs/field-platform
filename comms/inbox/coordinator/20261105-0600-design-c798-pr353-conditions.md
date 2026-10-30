VERDICT: C-798 PASS WITH CONDITIONS on 5d5cbf733c73875f279f6a47dca00ac9be157eaa (PR 353, was 783a85f; one new commit, 5d5cbf7). Conditions 1, 2, 3 and 4 of my C-698 are closed as stated. Two residual holes of the same class as condition 2 remain (a non-string build context and a non-string env_file entry still read as clean). Cloud container; no docker run; UNVERIFIED on any estate.

## C-698 conditions and state at this head (observed with the same probes)
1. Invalid UTF-8 model exited 1 with a traceback: now exit 3, "could not read the model (UnicodeDecodeError)", no traceback (tools/compose_resolved_check.py, ValueError added to the read handler). CLOSED. HIGH.
2. A non-string bind source passed as clean: now REFUSED, exit 2, for an int, a list and null ("volume: [1] is not a string"; the  argument of , applied to volume sources only). CLOSED for volumes. HIGH.
3. "Unknown shape" exited 2 for a list, an empty file and `services: 5`: now exit 3 with the shape message (a ValueError raised in place of the refusal). CLOSED. HIGH.
4. The sibling import under safe-path modes: with `-I`, `-P` and PYTHONSAFEPATH=1 the tool now runs (exit 0, no traceback; the tools directory is put on sys.path explicitly). CLOSED. HIGH.
5. Root trusted as given (`--repo-root /tmp` allows every source under /tmp; `/` refuses everything): not changed; now stated in the docstring as out of scope. ACCEPTED AS STATED. MEDIUM.
6. `--help` exits 0: unchanged; stated. ACCEPTED AS STATED. LOW.
7. Symlink roots under --realpath: unchanged and tested (152 tests in the two test files pass). Junction roots: not testable here, not tested. A root that resolves outside the repository: the operator's argument, as in 5.

## Objections first
1. THE NON-STRING CHECK COVERS VOLUME SOURCES ONLY. `must_be_text=True` is passed from the volume branch; a `build.context: 5` (int) and an `env_file: [5]` entry exit 0 "every bind source is allowed" (observed). Compose itself would not emit these, so it is the same low-likelihood malformed-model case the volume fix closed, left open for two sibling keys. A bind entry with no `source` key at all also passes (invalid compose; not a source). MEDIUM-LOW (observed).
2. "A MODEL THAT IS NOT A MAPPING WITH SERVICES" IS NOW 3, BUT A MODEL WITH `services: {}` (an empty mapping)? Not probed; I did not test the empty mapping. LOW.

## What I did NOT do
- No docker, no `--run-compose` beyond a missing-file case (exit 3).
- No junction test; no empty-services probe.
- Full-suite run: only the two compose-resolved test files (152 passed).
