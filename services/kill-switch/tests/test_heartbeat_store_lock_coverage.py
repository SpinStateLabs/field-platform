"""Every use of HeartbeatStore's shared sqlite3 connection is inside ``with self._lock``.

``kill_switch.store.HeartbeatStore`` keeps ONE sqlite3 connection shared by every
request thread (``check_same_thread=False``), so its lock must guard EVERY
use of that connection: writes, reads through the last fetch, the schema work
in ``__init__`` and ``close()``. The concurrency stress test
(tests/test_heartbeat_store_concurrency.py) catches unlocked READS, statistically. It did not catch
the lock removed from a write, from ``__init__`` or from ``close()``, and it
caught a cursor fetched after the lock was released 1 run in 5.

This test is structural and deterministic. It parses the store class with
``ast`` and fails on:

1. a ``self._conn`` use not lexically inside ``with self._lock`` -- an item
   listed BEFORE the lock in the same ``with`` is outside it, and a nested
   ``def``, ``lambda`` or generator expression never inherits the enclosing
   hold (it can run after release);
2. a cursor (``self._conn`` itself, or ``.execute()`` / ``.executemany()`` /
   ``.executescript()`` / ``.cursor()`` on one) bound to a name that is then
   used outside the hold it was bound in, returned, yielded, or stored on an
   attribute or item (fetch after release);
3. a method that takes the lock called while the lock is held (a plain
   ``threading.Lock`` deadlocks on itself);
4. ``self._lock`` used other than as ``with self._lock``, and any binding of
   ``self._conn`` / ``self._lock`` but the one in ``__init__``;
5. ``._conn`` touched anywhere in the package outside the class.

The only unlocked mention allowed is the ``self._conn = ...`` binding in
``__init__``. A private helper may use the connection without taking the
lock only when the same walk proves that every reference to it is a direct
call made while the lock is held (for example inside ``__init__``'s own
hold), or from a helper already proven that way, and that nothing outside the
class names it. That is proven per helper, never whitelisted by name.

``test_the_checker_rejects_each_unsafe_shape`` runs the checker on a small
store and on one mutation of it per rule, so the checker itself cannot
silently stop checking.
"""

from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

MODULE = "kill_switch.store"
CLASS = "HeartbeatStore"
CONN = "_conn"
LOCK = "_lock"

CURSOR_METHODS = frozenset({"execute", "executemany", "executescript", "cursor"})
LAZY_BUILTINS = frozenset({"iter", "map", "filter", "zip", "enumerate", "reversed"})
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.GeneratorExp, ast.ClassDef)

UNLOCKED = "uses self._conn without holding self._lock"
ESCAPES = "outside the lock hold it came from"
RETURNS = "returns a live cursor/connection"
YIELDS = "yields while holding self._lock"
STORES = "stores a live cursor/connection on an attribute or item"
DEADLOCK = "while holding it (plain Lock: self-deadlock)"
LOCK_USE = "uses self._lock other than as `with self._lock`"
BINDS = "binds self._conn/self._lock outside the one binding in __init__"
OUTSIDE = "touches ._conn outside the store class"
NO_BINDING = "no single `self._conn = ...` and `self._lock = threading.Lock()` in __init__"


def _self_attr(node: ast.AST, attr: str | None = None) -> str | None:
    if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "self" and (attr is None or node.attr == attr)):
        return node.attr
    return None


def _own_nodes(root: ast.AST):
    """Descendants of ``root`` in its own scope (nested scopes not entered)."""
    stack = list(ast.iter_child_nodes(root))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _SCOPES):
            stack.extend(ast.iter_child_nodes(node))


def _bound_pairs(node: ast.AST) -> list[tuple[ast.AST, ast.AST]]:
    if isinstance(node, ast.Assign):
        return [(t, node.value) for t in node.targets]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and node.value is not None:
        return [(node.target, node.value)]
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return [(node.optional_vars, node.context_expr)]
    return []


def _names(target: ast.AST) -> list[str]:
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]


@dataclass
class _Scope:
    method: str
    nested: bool
    tainted: set[str] = field(default_factory=set)
    binds: dict[str, set[int | None]] = field(default_factory=dict)
    loads: list[tuple[str, tuple[int, ...], int]] = field(default_factory=list)


@dataclass
class _Ref:
    caller: str
    nested: bool
    locked: bool
    is_call: bool
    line: int


@dataclass
class Report:
    violations: list[str] = field(default_factory=list)
    conn_methods: set[str] = field(default_factory=set)
    locked_uses: int = 0
    proven_helpers: set[str] = field(default_factory=set)


class _Checker:
    def __init__(self, cls: ast.ClassDef, label: str):
        self.cls, self.label = cls, label
        self.methods = {n.name: n for n in cls.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.report = Report()
        self.unlocked: dict[str, list[int]] = {}
        self.refs: dict[str, list[_Ref]] = {}
        self.holds_in: set[str] = set()
        self.call_funcs = {id(n.func) for n in ast.walk(cls) if isinstance(n, ast.Call)}
        self.lock_items = {id(i.context_expr) for n in ast.walk(cls)
                           if isinstance(n, (ast.With, ast.AsyncWith))
                           for i in n.items if _self_attr(i.context_expr, LOCK)}
        self.allowed_bindings: set[int] = set()
        self.plain_lock = True
        self._init_bindings()
        self.live_methods = self._live_methods()

    def violate(self, where: str, line: int, message: str) -> None:
        self.report.violations.append(f"{self.label}:{line} {where}: {message}")

    # -- the one binding of each attribute, top level of __init__ --------------
    def _init_bindings(self) -> None:
        init = self.methods.get("__init__")
        conn = lock = 0
        for stmt in init.body if init else []:
            if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
                continue
            target = stmt.targets[0]
            if _self_attr(target, CONN):
                conn += 1
                self.allowed_bindings.add(id(target))
            elif _self_attr(target, LOCK) and isinstance(stmt.value, ast.Call):
                func = stmt.value.func
                kind = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if kind in ("Lock", "RLock"):
                    lock += 1
                    self.plain_lock = kind == "Lock"
                    self.allowed_bindings.add(id(target))
        if (conn, lock) != (1, 1):
            self.violate("__init__", init.lineno if init else self.cls.lineno, NO_BINDING)

    # -- which expressions are a live cursor/connection ------------------------
    def _live(self, expr: ast.AST | None, tainted: set[str], live_methods: set[str]) -> bool:
        if expr is None:
            return False
        if _self_attr(expr, CONN) or (isinstance(expr, ast.Name) and expr.id in tainted):
            return True
        if isinstance(expr, ast.Call):
            func = expr.func
            if isinstance(func, ast.Attribute):
                if func.attr in CURSOR_METHODS and self._live(func.value, tainted, live_methods):
                    return True
                if _self_attr(func) in live_methods:
                    return True
            if isinstance(func, ast.Name) and func.id in LAZY_BUILTINS:
                return any(self._live(a, tainted, live_methods) for a in expr.args)
            return False
        if isinstance(expr, ast.IfExp):
            return any(self._live(e, tainted, live_methods) for e in (expr.body, expr.orelse))
        if isinstance(expr, ast.BoolOp):
            return any(self._live(e, tainted, live_methods) for e in expr.values)
        if isinstance(expr, (ast.NamedExpr, ast.Starred)):
            return self._live(expr.value, tainted, live_methods)
        if isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
            return any(self._live(e, tainted, live_methods) for e in expr.elts)
        return False

    def _taint(self, root: ast.AST, live_methods: set[str]) -> set[str]:
        tainted: set[str] = set()
        pairs = [p for n in _own_nodes(root) for p in _bound_pairs(n)]
        grew = True
        while grew:
            grew = False
            for target, value in pairs:
                if self._live(value, tainted, live_methods):
                    new = set(_names(target)) - tainted
                    if new:
                        tainted |= new
                        grew = True
        return tainted

    def _live_methods(self) -> set[str]:
        live: set[str] = set()
        grew = True
        while grew:
            grew = False
            for name, node in self.methods.items():
                if name in live:
                    continue
                tainted = self._taint(node, live)
                if any(isinstance(n, ast.Return) and self._live(n.value, tainted, live)
                       for n in _own_nodes(node)):
                    live.add(name)
                    grew = True
        return live

    # -- the walk ---------------------------------------------------------------
    def _new_scope(self, root: ast.AST, method: str, nested: bool) -> _Scope:
        return _Scope(method, nested, self._taint(root, self.live_methods))

    def _bind(self, target: ast.AST, holds: tuple[int, ...], scope: _Scope) -> None:
        for name in _names(target):
            scope.binds.setdefault(name, set()).add(holds[-1] if holds else None)

    def _unlocked_use(self, scope: _Scope, line: int) -> None:
        if scope.nested or scope.method == "__init__" or scope.method not in self.methods:
            self.violate(scope.method, line, UNLOCKED)
        else:
            self.unlocked.setdefault(scope.method, []).append(line)

    def _finish(self, scope: _Scope) -> None:
        for name, holds, line in scope.loads:
            bound = scope.binds.get(name, set())
            if any(h is not None and h in holds for h in bound):
                continue
            if not holds and None in bound:
                self._unlocked_use(scope, line)
            else:
                self.violate(scope.method, line, f"uses cursor `{name}` {ESCAPES}")

    def walk_method(self, node: ast.FunctionDef) -> None:
        scope = self._new_scope(node, node.name, nested=False)
        for stmt in node.body:
            self._walk(stmt, (), scope)
        self._finish(scope)

    def _walk(self, node: ast.AST, holds: tuple[int, ...], scope: _Scope) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            if not isinstance(node, ast.Lambda):
                for dec in node.decorator_list:
                    self._walk(dec, holds, scope)
            inner = self._new_scope(node, scope.method, nested=True)
            body = node.body if isinstance(node.body, list) else [node.body]
            for stmt in body:
                self._walk(stmt, (), inner)
            self._finish(inner)
            return
        if isinstance(node, ast.GeneratorExp):
            inner = self._new_scope(node, scope.method, nested=True)
            for child in ast.iter_child_nodes(node):
                self._walk(child, (), inner)
            self._finish(inner)
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            current = holds
            for item in node.items:
                self._walk(item.context_expr, current, scope)
                if _self_attr(item.context_expr, LOCK):
                    current = current + (id(item),)
                    self.holds_in.add(scope.method)
                if item.optional_vars is not None:
                    if self._live(item.context_expr, scope.tainted, self.live_methods):
                        self._bind(item.optional_vars, current, scope)
                    self._walk(item.optional_vars, current, scope)
            for stmt in node.body:
                self._walk(stmt, current, scope)
            return
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            value = node.value
            if value is not None:
                self._walk(value, holds, scope)
            live = self._live(value, scope.tainted, self.live_methods)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if live:
                    if not isinstance(target, (ast.Name, ast.Tuple, ast.List)):
                        self.violate(scope.method, node.lineno, STORES)
                    self._bind(target, holds, scope)
                self._walk(target, holds, scope)
            return
        if isinstance(node, ast.Return):
            if node.value is not None:
                self._walk(node.value, holds, scope)
                if self._live(node.value, scope.tainted, self.live_methods):
                    self.violate(scope.method, node.lineno, RETURNS)
            return
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            if holds:
                self.violate(scope.method, node.lineno, YIELDS)
            if node.value is not None:
                self._walk(node.value, holds, scope)
                if self._live(node.value, scope.tainted, self.live_methods):
                    self.violate(scope.method, node.lineno, RETURNS)
            return
        attr = _self_attr(node)
        if attr is not None:
            ctx_load = isinstance(node.ctx, ast.Load)
            if attr == CONN:
                if ctx_load:
                    self.report.conn_methods.add(scope.method)
                    if holds:
                        self.report.locked_uses += 1
                    else:
                        self._unlocked_use(scope, node.lineno)
                elif id(node) not in self.allowed_bindings:
                    self.violate(scope.method, node.lineno, BINDS)
            elif attr == LOCK:
                if ctx_load and id(node) not in self.lock_items:
                    self.violate(scope.method, node.lineno, LOCK_USE)
                elif not ctx_load and id(node) not in self.allowed_bindings:
                    self.violate(scope.method, node.lineno, BINDS)
            elif attr in self.methods:
                self.refs.setdefault(attr, []).append(_Ref(
                    scope.method, scope.nested, bool(holds), id(node) in self.call_funcs,
                    node.lineno))
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in scope.tainted:
            scope.loads.append((node.id, holds, node.lineno))
        for child in ast.iter_child_nodes(node):
            self._walk(child, holds, scope)

    # -- after the walk -----------------------------------------------------------
    def conclude(self, named_outside: set[str]) -> Report:
        proven: set[str] = set()
        grew = True
        while grew:  # least fixpoint: proven only upward from a call made under the lock
            grew = False
            for name in self.methods:
                refs = self.refs.get(name, [])
                if (name in proven or not name.startswith("_") or name.startswith("__")
                        or not refs or name in named_outside):
                    continue
                if all(r.is_call and (r.locked or (not r.nested and r.caller in proven))
                       for r in refs):
                    proven.add(name)
                    grew = True
        self.report.proven_helpers = proven
        for name, lines in self.unlocked.items():
            if name not in proven:
                for line in lines:
                    self.violate(name, line, UNLOCKED)

        acquires = set(self.holds_in)
        grew = True
        while grew:
            grew = False
            for callee, refs in self.refs.items():
                if callee in acquires:
                    for r in refs:
                        if r.is_call and r.caller not in acquires:
                            acquires.add(r.caller)
                            grew = True
        if self.plain_lock:
            for callee, refs in self.refs.items():
                if callee not in acquires:
                    continue
                for r in refs:
                    if r.is_call and (r.locked or (not r.nested and r.caller in proven)):
                        self.violate(r.caller, r.line,
                                     f"calls self.{callee}(), which takes self._lock, {DEADLOCK}")
        return self.report


def check_store(source: str, class_name: str, others: dict[str, str] | None = None,
                label: str = "store") -> Report:
    """Check ``class_name`` in ``source``; ``others`` maps label -> source of
    every other module in the package."""
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name]
    assert len(classes) == 1, f"{class_name} not found once in {label}"
    cls = classes[0]
    checker = _Checker(cls, label)
    for method in checker.methods.values():
        checker.walk_method(method)

    inside = {id(n) for n in ast.walk(cls)}
    helper_names = {m for m in checker.methods if m.startswith("_") and not m.startswith("__")}
    named_outside: set[str] = set()
    trees = [(label, tree)] + [(k, ast.parse(v)) for k, v in (others or {}).items()]
    for where, module in trees:
        for node in ast.walk(module):
            if not isinstance(node, ast.Attribute) or id(node) in inside:
                continue
            if node.attr == CONN:
                checker.violate(f"module {where}", node.lineno, OUTSIDE)
            if node.attr in helper_names:
                named_outside.add(node.attr)
    return checker.conclude(named_outside)


def test_every_connection_use_in_the_store_holds_the_lock():
    module = importlib.import_module(MODULE)
    path = Path(module.__file__)
    others = {str(p.relative_to(path.parent)): p.read_text(encoding="utf-8")
              for p in sorted(path.parent.rglob("*.py")) if p != path}
    report = check_store(path.read_text(encoding="utf-8"), CLASS, others, label=path.name)
    assert report.violations == [], "\n".join(report.violations)
    # non-vacuous: the walk saw the class doing real connection work
    assert {"__init__", "close"} <= report.conn_methods, report.conn_methods
    assert report.locked_uses >= 3, report.locked_uses


_GOOD = '''
import sqlite3
import threading


class S:
    def __init__(self, path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript("CREATE TABLE IF NOT EXISTS t (a)")
            self._migrate()

    def _migrate(self):
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(t)")}
        if "b" not in cols:
            self._conn.execute("ALTER TABLE t ADD COLUMN b")

    def _fetch(self, a):
        return self._conn.execute("SELECT * FROM t WHERE a=?", (a,)).fetchone()

    def put(self, a):
        with self._lock, self._conn:
            cur = self._conn.execute("INSERT INTO t VALUES (?, NULL)", (a,))
            count = cur.rowcount
            return count, self._fetch(a)

    def get(self, a):
        with self._lock:
            row = self._fetch(a)
        return row

    def rows(self):
        with self._lock:
            return self._conn.execute("SELECT * FROM t").fetchall()

    def size(self):
        return len(self.rows())

    def close(self):
        with self._lock:
            self._conn.close()
'''

_MUTATIONS = {  # name: (text in _GOOD, replacement, message the checker must report)
    "write_unlocked": (
        "with self._lock, self._conn:\n            cur =",
        "with self._conn:\n            cur =", UNLOCKED),
    "lock_taken_after_the_connection": (
        "with self._lock, self._conn:\n            cur =",
        "with self._conn, self._lock:\n            cur =", UNLOCKED),
    "init_unlocked": (
        "with self._lock, self._conn:\n            self._conn.row_factory",
        "with self._conn:\n            self._conn.row_factory", UNLOCKED),
    "close_unlocked": (
        "with self._lock:\n            self._conn.close()",
        "if True:\n            self._conn.close()", UNLOCKED),
    "fetch_after_release": (
        'with self._lock:\n            return self._conn.execute("SELECT * FROM t").fetchall()',
        'with self._lock:\n            cur = self._conn.execute("SELECT * FROM t")\n'
        "        return cur.fetchall()", ESCAPES),
    "cursor_returned": (
        'return self._conn.execute("SELECT * FROM t").fetchall()',
        'return self._conn.execute("SELECT * FROM t")', RETURNS),
    "cursor_stored_on_attribute": (
        "cur = self._conn.execute(", "self.last = cur = self._conn.execute(", STORES),
    "helper_called_unlocked": (
        "    def size(self):",
        "    def peek(self, a):\n        return self._fetch(a)\n\n    def size(self):", UNLOCKED),
    "helper_passed_as_a_value": (
        "    def size(self):",
        "    def peek(self):\n        fetch = self._fetch\n        with self._lock:\n"
        "            return fetch(1)\n\n    def size(self):", UNLOCKED),
    "lambda_inside_the_hold": (
        "count = cur.rowcount",
        "count = cur.rowcount\n            later = lambda: self._conn.commit()", UNLOCKED),
    "locked_method_called_inside_the_hold": (
        "with self._lock:\n            return self._conn.execute",
        "with self._lock:\n            self.get(1)\n            return self._conn.execute", DEADLOCK),
    "yield_inside_the_hold": (
        'return self._conn.execute("SELECT * FROM t").fetchall()',
        'yield from self._conn.execute("SELECT * FROM t").fetchall()', YIELDS),
    "manual_acquire": (
        "        with self._lock:\n            self._conn.close()",
        "        self._lock.acquire()\n        try:\n            self._conn.close()\n"
        "        finally:\n            self._lock.release()", LOCK_USE),
    "connection_rebound": (
        "            self._conn.close()",
        "            self._conn.close()\n            self._conn = None", BINDS),
    "connection_touched_outside_the_class": (
        "\n\nclass S:",
        "\n\ndef peek(store):\n    return store._conn.total_changes\n\n\nclass S:", OUTSIDE),
}


def test_the_checker_rejects_each_unsafe_shape():
    good = check_store(_GOOD, "S")
    assert good.violations == [], good.violations
    assert {"_migrate", "_fetch"} <= good.proven_helpers, good.proven_helpers
    missed = []
    for name, (old, new, message) in _MUTATIONS.items():
        assert _GOOD.count(old) == 1, name
        report = check_store(_GOOD.replace(old, new), "S")
        if not any(message in v for v in report.violations):
            missed.append(f"{name}: {report.violations}")
    assert not missed, missed


@pytest.mark.parametrize("helper_call", ["self._migrate()", "self._fetch(1)"])
def test_a_helper_is_proven_through_private_callers_only_from_a_locked_call(helper_call):
    """A connection-free private helper in between neither blocks the proof
    (when it is called under the lock) nor fakes it (when it is not)."""
    relay = f"    def _relay(self):\n        return {helper_call}\n\n    def size(self):"
    with_relay = _GOOD.replace("    def size(self):", relay)
    locked_entry = with_relay.replace(
        "            row = self._fetch(a)\n", "            row = self._fetch(a)\n            self._relay()\n")
    assert check_store(locked_entry, "S").violations == []
    unlocked_entry = with_relay.replace(
        "        return len(self.rows())", "        self._relay()\n        return len(self.rows())")
    for source in (unlocked_entry, with_relay):  # called unlocked / never called
        report = check_store(source, "S")
        assert any(UNLOCKED in v for v in report.violations), report.violations
