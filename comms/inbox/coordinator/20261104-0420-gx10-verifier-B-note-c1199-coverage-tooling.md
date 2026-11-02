gx10 verifier B: note on C-1199 part 1 (Lane 13 report 20261102-2330-builder-lane13-c1199-report.md says no coverage tool is installed locally and offers a GX10 slot as one way out). Measured, read-only, nothing installed or changed.

- The GX10 test venv (~/ff-work/venv-fp, Python 3.12.3) has neither `coverage` nor `pytest_cov` (importlib find_spec: both False). So a GX10 slot alone does not unblock part 1.
- Unblock needs a download of both packages from the package index into a NEW throwaway venv (not the shared test venv, which the verifiers' full runs use). I will not install into the shared venv and will not download without Don's OK.
- If Don approves: I can create the throwaway venv on the GX10, run each suite with --cov on a named main head, and report per-file line coverage (about one full-suite wall time, plus the coverage overhead; the tools suite is the long one at 8.6 min plain). Say which main sha and that the download is approved, and name me or verifier A for it.
- Note for the coordinator: C-1199 is claimed by Lane 13 (part 2 reported); I am not claiming it.
