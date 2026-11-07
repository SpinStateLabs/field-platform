"""S9-24: ``SentinelEngine.ledger_appends_dropped`` is incremented from the request threadpool (the /check route is a
sync ``def``), so the increment is made under ``self._drops_lock``, as federation-broker's engine does. A bare ``+=`` is a
read, an add and a store: two threads can lose an update.

1. a threaded test: 8 threads x 2000 ``_note_drop`` calls with a 1 microsecond switch interval, the counter equals the
   number of calls (loss is probabilistic, so this is statistical);
2. a structural pin, deterministic: every write of the counter other than the initial ``= 0`` is an ``+= 1`` lexically
   inside ``with self._drops_lock``, so removing the lock from the increment fails here every time."""
from __future__ import annotations

import ast
import inspect
import sys
import threading

import pytest

from conformance_sentinel import engine as engine_module
from conformance_sentinel.engine import SentinelEngine

COUNTER, LOCK = "ledger_appends_dropped", "_drops_lock"


def make_engine() -> SentinelEngine:
    return SentinelEngine(registry=None, delegation=None, governor=None, ledger=None, ledger_health=lambda: True,
                          manifests=None)


def test_the_counter_starts_at_zero_and_counts_one_per_drop():
    e = make_engine()
    assert getattr(e, COUNTER) == 0
    e._note_drop("sentinel.judge", RuntimeError("x"))
    e._note_drop("sentinel.judge", RuntimeError("x"))
    assert getattr(e, COUNTER) == 2


def test_concurrent_drops_are_all_counted():
    e = make_engine()
    threads_n, calls = 8, 2000
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        barrier = threading.Barrier(threads_n)

        def work():
            barrier.wait()
            for _ in range(calls):
                e._note_drop("sentinel.judge", RuntimeError("x"))

        threads = [threading.Thread(target=work) for _ in range(threads_n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old)
    assert getattr(e, COUNTER) == threads_n * calls


# -- structural pin -----------------------------------------------------------------------------------------------------
def counter_writes(source: str):
    """(augassign nodes, plain assign nodes) that write ``self.<COUNTER>`` in the SentinelEngine class, each with the
    names of the lock attributes held by the ``with`` blocks around it."""
    tree = ast.parse(source)
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "SentinelEngine")
    found: list[tuple[ast.AST, str, bool]] = []

    def is_counter(t):
        return isinstance(t, ast.Attribute) and t.attr == COUNTER and isinstance(t.value, ast.Name) and t.value.id == "self"

    def visit(node, held: bool, func: str):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func, held = node.name, False
        if isinstance(node, ast.With):
            holds = any(isinstance(i.context_expr, ast.Attribute) and i.context_expr.attr == LOCK
                        and isinstance(i.context_expr.value, ast.Name) and i.context_expr.value.id == "self"
                        for i in node.items)
            for child in node.body:
                visit(child, held or holds, func)
            return
        if isinstance(node, ast.AugAssign) and is_counter(node.target):
            found.append((node, func, held))
        if isinstance(node, ast.Assign) and any(is_counter(t) for t in node.targets):
            found.append((node, func, held))
        for child in ast.iter_child_nodes(node):
            visit(child, held, func)

    for item in cls.body:
        visit(item, False, "<class>")
    return found


def violations(source: str) -> list[str]:
    out = []
    writes = counter_writes(source)
    if not any(isinstance(n, ast.AugAssign) for n, _, _ in writes):
        out.append("no increment found")
    for node, func, held in writes:
        if isinstance(node, ast.AugAssign):
            if not held:
                out.append(f"{func}: the increment is not inside 'with self.{LOCK}'")
        elif func != "__init__" or not (isinstance(node.value, ast.Constant) and node.value.value == 0):
            out.append(f"{func}: the counter is assigned outside __init__'s initial 0")
    if f"self.{LOCK} = threading.Lock()" not in source:
        out.append(f"__init__ does not create self.{LOCK} = threading.Lock()")
    return out


def test_the_increment_is_inside_the_lock_in_the_real_engine():
    assert violations(inspect.getsource(engine_module)) == []


GOOD = '''
import threading
class SentinelEngine:
    def __init__(self):
        self.ledger_appends_dropped = 0
        self._drops_lock = threading.Lock()
    def _note_drop(self):
        with self._drops_lock:
            self.ledger_appends_dropped += 1
'''


@pytest.mark.parametrize("name,source,expect", [
    ("unlocked increment", GOOD.replace("        with self._drops_lock:\n            self.ledger_appends_dropped += 1",
                                        "        self.ledger_appends_dropped += 1"), "not inside"),
    ("lock released before the increment", GOOD.replace("with self._drops_lock:\n            self.ledger_appends_dropped += 1",
                                                       "with self._drops_lock:\n            pass\n        self.ledger_appends_dropped += 1"),
     "not inside"),
    ("another lock", GOOD.replace("with self._drops_lock:", "with self._other:"), "not inside"),
    ("nested function does not inherit the hold", GOOD.replace(
        "            self.ledger_appends_dropped += 1",
        "            def later():\n                self.ledger_appends_dropped += 1"), "not inside"),
    ("plain assignment elsewhere", GOOD + "    def reset(self):\n        self.ledger_appends_dropped = 5\n", "assigned outside"),
    ("no lock created", GOOD.replace("        self._drops_lock = threading.Lock()\n", ""), "does not create"),
    ("no increment", GOOD.replace("self.ledger_appends_dropped += 1", "pass"), "no increment"),
])
def test_the_checker_rejects_each_unsafe_shape(name, source, expect):
    assert any(expect in v for v in violations(source)), (name, violations(source))


def test_the_checker_accepts_the_good_shape():
    assert violations(GOOD) == []
