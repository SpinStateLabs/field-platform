"""C-1206: `field_agent.actions` is a pure re-export of the sentinel's client surface; pin the module itself.

No test imported `field_agent.actions` by name (C-1199 part 2). The package-level identity test goes through
`field_agent/__init__.py`, which imports from this module, so it sees a changed class but not a changed `__all__`
or a locally defined name that is not re-exported by the package. These tests read the module directly: its public
surface, that every name is the sentinel's own object, and that the file adds no definition of its own ("the SDK adds
no verdict logic of its own", the module docstring). All values are made up; nothing is read from the environment."""
from __future__ import annotations

import ast
from pathlib import Path

import conformance_sentinel.governed as governed_mod
import field_agent
from field_agent import actions

NAMES = ("ActionBlocked", "ActionEscalated", "Governor", "governed")
SOURCE = Path(actions.__file__)


def test_the_public_surface_is_exactly_the_four_names():
    assert sorted(actions.__all__) == sorted(NAMES)


def test_every_name_is_the_sentinels_own_object_not_a_copy_or_a_subclass():
    for name in NAMES:
        assert getattr(actions, name) is getattr(governed_mod, name), name


def test_the_package_exports_the_same_objects_as_the_module():
    for name in NAMES:
        assert getattr(field_agent, name) is getattr(actions, name), name
        assert name in field_agent.__all__, name


def test_the_module_defines_no_class_function_or_assignment_of_its_own():
    """A re-export file: imports and one __all__ list, nothing else (the docstring is the only other statement)."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    own = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            own.append(f"def {node.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if names != ["__all__"]:
                own.append(f"assign {names}")
    assert own == [], own


def test_an_unknown_attribute_is_not_quietly_provided():
    for name in ("Blocked", "check", "verdict"):
        assert not hasattr(actions, name), name
