"""C-1192: a fixed, file-level split of the tools test suite, for `pytest --shard I/N` (see conftest.py).

The GX10 full run spends 518 s of 918 s in tools/tests, and five files are 76 percent of that (C-1135 profile). A
runner that wants a shorter wall time starts N copies of pytest, one per shard, and every test file lands in exactly
one of them. The split is by FILE, never by test, so a module-level fixture or a parametrised family stays together.

Balance is greedy longest-first: files are taken heaviest first and each goes to the lightest shard so far (ties go to
the lowest shard number). The weights are the seconds the C-1135 profile measured on the GX10 for the heavy files; a
file not listed weighs `DEFAULT_WEIGHT`. Stated limit: the weights are one profile of one run on main 05942b98, so
they steer the balance, they are not a promise; a wrong weight only unbalances the shards, it never loses a file.
"""
from __future__ import annotations

#: seconds on the GX10, C-1135 (20261102-0300-gx10-verifier-A-c1135-profile.md); the other files are about 1.4 s each
WEIGHTS: dict[str, float] = {
    "test_topology_lint.py": 108.4,
    "test_phase_g_check.py": 102.7,
    "test_renew_token.py": 75.2,
    "test_fly_identity_c5.py": 65.9,
    "test_estate_probe.py": 36.8,
    "test_operator_cli_c2.py": 20.8,
    "test_estate_kill_watcher.py": 15.7,
    "test_environment_doc.py": 15.5,
}
DEFAULT_WEIGHT = 1.4


def parse_spec(spec: str) -> tuple[int, int]:
    """`I/N` with 1 <= I <= N -> (I, N); anything else raises ValueError."""
    left, sep, right = spec.partition("/")
    if not sep or not left.isdigit() or not right.isdigit():
        raise ValueError(f"--shard wants I/N, for example 2/3 (got {spec!r})")
    index, total = int(left), int(right)
    if not 1 <= index <= total:
        raise ValueError(f"--shard I/N needs 1 <= I <= N (got {spec!r})")
    return index, total


def assign(files: list[str], total: int) -> dict[str, int]:
    """File name -> shard number (1-based) for every distinct name in `files`; the same input gives the same answer."""
    names = sorted(set(files), key=lambda f: (-WEIGHTS.get(f, DEFAULT_WEIGHT), f))
    load = [0.0] * total
    out: dict[str, int] = {}
    for name in names:
        lightest = min(range(total), key=lambda i: (load[i], i))
        out[name] = lightest + 1
        load[lightest] += WEIGHTS.get(name, DEFAULT_WEIGHT)
    return out
