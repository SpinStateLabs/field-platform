"""C-1192: `pytest --shard I/N` runs only the test files assigned to shard I of N (see _sharding.py).

Without the option nothing changes: every test is collected as before. With it, the tests of the other shards are
deselected (they show as "deselected", not as skipped), so N copies of pytest started with 1/N .. N/N, on the same
collection, together run every test exactly once."""
from __future__ import annotations

import pytest

from _sharding import assign, parse_spec


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--shard", default=None, metavar="I/N",
                     help="run only the test files assigned to shard I of N (1-based); the shards are file-level")


def pytest_configure(config: pytest.Config) -> None:
    spec = config.getoption("--shard")
    if spec is not None:
        try:
            parse_spec(spec)   # a bad spec stops the run here, before anything is collected
        except ValueError as exc:
            raise pytest.UsageError(str(exc)) from None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    spec = config.getoption("--shard")
    if spec is None:
        return
    index, total = parse_spec(spec)
    owner = assign([item.path.name for item in items], total)
    keep = [item for item in items if owner[item.path.name] == index]
    drop = [item for item in items if owner[item.path.name] != index]
    if drop:
        config.hook.pytest_deselected(items=drop)
    items[:] = keep
