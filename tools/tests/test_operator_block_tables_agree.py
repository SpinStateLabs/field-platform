"""S11-32: the G16 (stage 0) and G18 (stage 1 window) gates judge the SAME eight operator-block services.

`OPERATOR_BLOCK_SERVICES` was defined twice, in tools/phase_g_stage0_check.py and tools/stage1_window.py (the G18 module
derived its REQUIRED_LABELS from its own copy). Only the stage 0 copy was pinned to a literal, so a ninth service added to
one file left the two gates judging different estates with every test green. This pins that the two tables are one
(equal, in order), that `REQUIRED_LABELS` follows them, and that every row agrees with estate_probe's service list.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0]))

import estate_probe as ep  # noqa: E402
import phase_g_stage0_check as stage0  # noqa: E402
import stage1_window as stage1  # noqa: E402


def test_the_two_gates_judge_the_same_services_in_the_same_order():
    assert tuple(stage1.OPERATOR_BLOCK_SERVICES) == tuple(stage0.OPERATOR_BLOCK_SERVICES)


def test_each_row_is_equal_label_path_and_service_name():
    pairs = list(zip(stage0.OPERATOR_BLOCK_SERVICES, stage1.OPERATOR_BLOCK_SERVICES))
    assert len(stage0.OPERATOR_BLOCK_SERVICES) == len(stage1.OPERATOR_BLOCK_SERVICES) == 8
    for a, b in pairs:
        assert a == b, (a, b)


def test_the_stage1_required_labels_are_the_stage0_labels():
    assert tuple(stage1.REQUIRED_LABELS) == tuple(label for label, _p, _s in stage0.OPERATOR_BLOCK_SERVICES)


def test_labels_are_unique_and_every_row_is_a_three_string_tuple():
    for table in (stage0.OPERATOR_BLOCK_SERVICES, stage1.OPERATOR_BLOCK_SERVICES):
        assert len({label for label, _p, _s in table}) == len(table)
        assert all(isinstance(row, tuple) and len(row) == 3 and all(isinstance(x, str) and x for x in row)
                   for row in table)


def test_every_row_agrees_with_estate_probes_service_list():
    """The console owns the proxy root (bare /health, not in estate_probe.SERVICES); every other row is
    /<label>/health for the service estate_probe names under that label."""
    for table in (stage0.OPERATOR_BLOCK_SERVICES, stage1.OPERATOR_BLOCK_SERVICES):
        for label, path, service in table:
            if label == "console":
                assert (path, service) == ("/health", "ops-console")
                continue
            assert path == f"/{label}/health", (label, path)
            assert ep.SERVICES.get(label) == service, (label, service, ep.SERVICES.get(label))


def test_the_two_names_are_one_object_or_equal_by_value():
    """After the shared definition they are literally one tuple; the equality above is the contract either way."""
    assert stage1.OPERATOR_BLOCK_SERVICES == stage0.OPERATOR_BLOCK_SERVICES
