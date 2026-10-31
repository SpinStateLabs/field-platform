"""C-505 (Lane 10 error-echo note, section 4 item 4): non-test code must not put a value from outside its trust into
an error message, an API reply, a CLI line or a log line.

A value from outside the function's trust is: a response body (`.text`, `.content`, `.json()` of a response, a
`_body(resp)` helper), response `.headers`, the text of a caught exception (`{exc}`, `str(exc)`, `repr(exc)`, a bare
`exc` passed on), or an environment value (`os.environ[..]`, `os.environ.get(..)`, `os.getenv(..)`). The safe shapes are
a fixed text, a status code, and `type(exc).__name__`. This is an AST scan (the C-57 lint shape) of the non-test
Python under `packages/*/src`, `services/*/src` and `tools/`. A sink is:

* `api-reply`:   `HTTPException(..)`, `JSONResponse(..)`, `Response(..)` and the other response classes;
* `error`:       a constructor whose name ends in `Error` (and `Exception`, `BadParameter`, `UsageError`);
* `reply-field`: a `detail=` / `error=` / `message=` / `reason=` / `note=` / `msg=` keyword of any call (the result
                 objects that an API returns to a caller);
* `cli`:         `typer.echo(..)`, `click.echo(..)`, `print(..)`;
* `log`:         `<logger>.debug|info|warning|error|exception|critical(..)`.

A tainted value anywhere in the sink's arguments is a finding, unless it sits under `type(..)`, `.__class__`, `len(..)`,
`bool(..)`, `isinstance(..)` or a comparison. A local name assigned from a tainted expression is tainted too, one
assignment deep (`x = resp.text` then `f"..{x}"`), also through tuple unpacking (`a, b = resp.text, 1`), an augmented
assignment (`m += resp.text`), an annotated assignment and a walrus; a name assigned from a tainted name is not followed.

Limits (the lint is a floor, not a proof; a pass is not "no echo anywhere"): a taint two assignments deep; a dict or list
literal that is returned or passed on without a sink (`return {"detail": resp.json()}`); an attribute or subscript target
(`self.x = resp.text`); a starred unpack; a source that has another name (a response held in a name not in RESP_NAMES,
a request body); a sink spelled another way (`sys.stderr.write`, `typer.secho`, `logging.getLogger(..).error`, a logger
held in a call result); a value rebuilt by an arbitrary function call. A new sink spelling or source name is added here,
with a corpus case, when it shows up.

Known sites are listed in `boundary_echo_allowlist.txt` as `path::function::kind = count | tag | reason`:

* `allow`: the site stays (an operator terminal, a fixed text built from a class name, a test fixture). The count must
  equal the scan: a new site fails, and so does an entry whose site is gone while its file still exists.
* `pending-<N>`: PR <N> fixes the site. The count may fall to zero and the entry may sit in the list, so the lint is
  green before and after that PR lands, in any merge order; it can never rise and a new site never gets a pending tag.
  When every pending entry of one PR has fallen to zero the lint warns: delete the lines.

An entry whose file is not in the scanned tree is skipped (the file may not exist at this base). Files that do not
parse are named and fail the lint. The scan reads every file it should: the blindness control counts the files and the
sinks it examined, independently of the allowlist.
"""
from __future__ import annotations

import ast
import sys
import warnings
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("boundary_echo_allowlist.txt")
MIN_FILES = 100      # blindness floors: the scan must examine at least this many files and sinks
MIN_SINKS = 600
SKIP_DIRS = {"tests", "node_modules", "__pycache__", ".venv", "venv", ".git", "build", "dist", "examples"}

RESPONSE_CLASSES = {"HTTPException", "JSONResponse", "Response", "PlainTextResponse", "HTMLResponse", "ORJSONResponse",
                    "UJSONResponse", "StreamingResponse"}
ERROR_NAMES = {"BadParameter", "UsageError", "Exception"}
FIELD_KEYWORDS = {"detail", "error", "message", "reason", "note", "msg"}
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical"}
RESP_NAMES = {"resp", "response", "r", "res", "rev", "mresp", "cresp", "reply", "answer", "upstream", "rv", "rs",
              "result", "listing", "loaded", "patch", "r2", "rr", "raw"}
RESP_ATTRS = {"response", "resp", "_resp", "_response"}
BODY_HELPERS = {"_body", "_text", "body_of"}
SAFE_CALLS = {"type", "len", "bool", "isinstance", "id", "append_failure_status", "_registry_reason"}   # the last two return a status / a class name only
SAFE_ATTRS = {"__class__", "__name__"}
PASS_METHODS = {"strip", "rstrip", "lstrip", "lower", "upper", "decode", "encode", "format", "get", "split", "join", "replace"}


def _is_test_file(rel: Path) -> bool:
    return rel.name.startswith("test_") or rel.name == "conftest.py" or any(p in SKIP_DIRS for p in rel.parts)


def python_files() -> list[Path]:
    out: list[Path] = []
    for top in ("packages", "services"):
        for src in sorted((ROOT / top).glob("*/src")):
            out += [p for p in src.rglob("*.py") if not _is_test_file(p.relative_to(ROOT))]
    tools = ROOT / "tools"
    if tools.is_dir():
        out += [p for p in tools.rglob("*.py") if not _is_test_file(p.relative_to(ROOT))]
    return sorted(set(out))


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _sink_kind(call: ast.Call) -> str | None:
    name = _call_name(call.func)
    if name is None:
        return None
    if name in RESPONSE_CLASSES:
        return "api-reply"
    if name.endswith("Error") or name in ERROR_NAMES:
        return "error"
    if isinstance(call.func, ast.Name) and name == "print":
        return "cli"
    if isinstance(call.func, ast.Attribute) and name == "echo":
        return "cli"
    if isinstance(call.func, ast.Attribute) and name in LOG_METHODS and isinstance(call.func.value, (ast.Name, ast.Attribute)):
        return "log"
    return None


class _Scan(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.exc: list[str] = []                    # names bound by the enclosing `except .. as name`
        self.alias: list[set[str]] = [set()]        # per function: names assigned from a tainted expression
        self.found: Counter[tuple[str, str]] = Counter()   # (function, kind)
        self.sinks: int = 0                         # every sink examined, tainted or not

    # --- scope ------------------------------------------------------------------------------------------------
    def _func(self, node: ast.AST, name: str) -> None:
        self.stack.append(name)
        self.alias.append(set())
        outer, self.exc = self.exc, []
        self.generic_visit(node)
        self.exc = outer
        self.alias.pop()
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        self.exc.append(node.name or "")
        for stmt in node.body:
            self.visit(stmt)
        self.exc.pop()

    # --- taint ------------------------------------------------------------------------------------------------
    def _is_source(self, x: ast.AST, aliases: bool = True) -> bool:
        if isinstance(x, ast.Attribute):
            if x.attr in ("text", "content") and (
                    (isinstance(x.value, ast.Name) and x.value.id in RESP_NAMES)
                    or (isinstance(x.value, ast.Attribute) and x.value.attr in RESP_ATTRS)):
                return True
            if x.attr == "headers":
                return True
            if x.attr == "environ" and isinstance(x.value, ast.Name) and x.value.id == "os":
                return True
            if x.attr in ("args", "message") and isinstance(x.value, ast.Name) and x.value.id in self._excnames():
                return True
        if isinstance(x, ast.Call):
            name = _call_name(x.func)
            if name in BODY_HELPERS and isinstance(x.func, ast.Name):
                return True
            if name == "getenv" and (isinstance(x.func, ast.Attribute) or isinstance(x.func, ast.Name)):
                return True
            if (name == "json" and isinstance(x.func, ast.Attribute) and isinstance(x.func.value, ast.Name)
                    and x.func.value.id in RESP_NAMES and not x.args):
                return True
        if isinstance(x, ast.Name):
            return x.id in self._excnames() or (aliases and x.id in self.alias[-1])
        return False

    def _excnames(self) -> set[str]:
        return {n for n in self.exc if n}

    def tainted(self, e: ast.AST, aliases: bool = True) -> bool:
        """True if a tainted value appears in `e` outside a safe wrapper (`aliases=False`: direct sources only)."""
        if isinstance(e, ast.Call):
            name = _call_name(e.func)
            if name in SAFE_CALLS:
                return False
        if isinstance(e, ast.Attribute) and e.attr in SAFE_ATTRS:
            return False
        if (isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id in self._excnames()
                and e.attr not in ("args", "message")):
            return False   # `exc.status`, `exc.detail`: a field of the service's own exception class, not its text
        if isinstance(e, ast.Compare):
            return False
        if self._is_source(e, aliases):
            return True
        return any(self.tainted(c, aliases) for c in ast.iter_child_nodes(e))

    # --- sinks ------------------------------------------------------------------------------------------------
    def _derived(self, e: ast.AST) -> bool:
        """True if `e` is a direct source or a plain rewrite of one (interpolation, str(), .strip(), `x or y`); an alias
        is not followed, and the result of an arbitrary call over a source is not tainted."""
        if self._is_source(e, aliases=False):
            return True
        if isinstance(e, (ast.JoinedStr, ast.BinOp)):
            return self.tainted(e, aliases=False)
        if isinstance(e, ast.BoolOp):
            return any(self._derived(v) for v in e.values)
        if isinstance(e, ast.IfExp):
            return self._derived(e.body) or self._derived(e.orelse)
        if isinstance(e, ast.Call):
            name = _call_name(e.func)
            if isinstance(e.func, ast.Name) and name in ("str", "repr"):
                return any(self._derived(a) for a in e.args)
            if isinstance(e.func, ast.Attribute) and name in PASS_METHODS:
                return self._derived(e.func.value) or any(self._derived(a) for a in e.args)
        return False

    def _bind(self, target: ast.AST, value: ast.AST) -> None:
        """Mark the names `target` binds from `value` (a tuple target is matched element by element)."""
        if isinstance(target, ast.Name):
            if self._derived(value):
                self.alias[-1].add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts) and not any(
                    isinstance(e, ast.Starred) for e in target.elts + value.elts):
                for t, v in zip(target.elts, value.elts):
                    self._bind(t, v)
            elif self._derived(value):
                for t in target.elts:
                    self._bind(t, value)

    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            self._bind(t, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._bind(node.target, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name) and self._derived(node.value):
            self.alias[-1].add(node.target.id)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._bind(node.target, node.value)
        self.generic_visit(node)

    def _record(self, kind: str) -> None:
        self.found[(".".join(self.stack) or "<module>", kind)] += 1

    def visit_Call(self, node: ast.Call) -> None:
        kind = _sink_kind(node)
        hit = False
        if kind is not None:
            self.sinks += 1
            hit = any(self.tainted(a) for a in node.args) or any(
                self.tainted(k.value) for k in node.keywords if k.arg != "extra")
            if hit:
                self._record(kind)
        # a result object carries a detail/error/message field back to a caller
        for k in node.keywords:
            if k.arg in FIELD_KEYWORDS and self.tainted(k.value):
                if not (hit and kind in ("api-reply", "error")):
                    self._record("reply-field")
                    break
        self.generic_visit(node)


def scan_source(source: str) -> tuple[Counter[tuple[str, str]], int]:
    s = _Scan()
    s.visit(ast.parse(source))
    return s.found, s.sinks


def scan_repo() -> tuple[Counter[str], int, int, list[str]]:
    """(findings by path::function::kind, files scanned, sinks examined, unparsable files)."""
    out: Counter[str] = Counter()
    files = sinks = 0
    bad: list[str] = []
    for p in python_files():
        rel = p.relative_to(ROOT).as_posix()
        try:
            found, n = scan_source(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            bad.append(rel)
            continue
        files += 1
        sinks += n
        for (fn, kind), c in found.items():
            out[f"{rel}::{fn}::{kind}"] += c
    return out, files, sinks, bad


# --- allowlist ----------------------------------------------------------------------------------------------------
def parse_allowlist(text: str) -> dict[str, tuple[int, str]]:
    """key -> (count, tag). A malformed line, a bad tag, a missing reason or a duplicate key raises ValueError."""
    out: dict[str, tuple[int, str]] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", 2)]
        if len(parts) != 3 or not parts[2]:
            raise ValueError(f"line {n}: want `key = count | tag | reason`")
        key, _, count = parts[0].rpartition(" = ")
        tag = parts[1]
        if not key or not count.isdigit():
            raise ValueError(f"line {n}: bad key or count")
        if tag != "allow" and not (tag.startswith("pending-") and tag[8:].isdigit()):
            raise ValueError(f"line {n}: tag must be allow or pending-<N>")
        if key in out:
            raise ValueError(f"line {n}: duplicate key")
        out[key] = (int(count), tag)
    return out


def problems(found: Counter[str], allow: dict[str, tuple[int, str]], scanned_files: set[str]) -> tuple[list[str], list[str]]:
    """(failures, warnings) of the scan against the allowlist."""
    bad: list[str] = []
    for key, n in sorted(found.items()):
        if key not in allow:
            bad.append(f"new site: {key} x{n}")
            continue
        cnt, tag = allow[key]
        if tag == "allow" and n != cnt:
            bad.append(f"count changed: {key} scan {n}, list {cnt}")
        elif tag != "allow" and n > cnt:
            bad.append(f"pending site rose: {key} scan {n}, list {cnt}")
    for key, (cnt, tag) in sorted(allow.items()):
        path = key.split("::", 1)[0]
        if path not in scanned_files:
            continue
        if tag == "allow" and found.get(key, 0) == 0:
            bad.append(f"stale entry: {key}")
    warn: list[str] = []
    by_pr: dict[str, list[str]] = {}
    for key, (cnt, tag) in allow.items():
        if tag != "allow" and key.split("::", 1)[0] in scanned_files:
            by_pr.setdefault(tag, []).append(key)
    for tag, keys in sorted(by_pr.items()):
        if all(found.get(k, 0) == 0 for k in keys):
            warn.append(f"every {tag} entry is at zero: delete those lines")
    return bad, warn


def test_boundary_echo_scan_matches_allowlist():
    found, nfiles, nsinks, bad_files = scan_repo()
    assert not bad_files, f"files that do not parse: {bad_files}"
    allow = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    scanned = {p.relative_to(ROOT).as_posix() for p in python_files()}
    bad, warn = problems(found, allow, scanned)
    for w in warn:
        warnings.warn(w)
    assert not bad, "\n".join(bad)


def test_scan_is_not_blind():
    _, nfiles, nsinks, bad_files = scan_repo()
    assert not bad_files
    assert nfiles >= MIN_FILES, nfiles
    assert nsinks >= MIN_SINKS, nsinks


# --- scanner corpus: one case per sink kind and source kind --------------------------------------------------------
def _hits(src: str) -> dict[tuple[str, str], int]:
    return dict(scan_source(src)[0])


@pytest.mark.parametrize("src,kind", [
    ("def f(exc):\n    try:\n        pass\n    except Exception as exc:\n        raise HTTPException(502, str(exc))\n", "api-reply"),
    ("def f():\n    try:\n        pass\n    except Exception as exc:\n        raise RuntimeError(f'x {exc}')\n", "error"),
    ("def f(resp):\n    return Item(detail=resp.text)\n", "reply-field"),
    ("def f():\n    try:\n        pass\n    except Exception as exc:\n        print(exc)\n", "cli"),
    ("def f():\n    try:\n        pass\n    except Exception as exc:\n        log.warning('x %s', exc)\n", "log"),
])
def test_each_sink_kind_is_found(src, kind):
    assert _hits(src) == {("f", kind): 1}


@pytest.mark.parametrize("expr", [
    "resp.text", "resp.content", "self._resp.text", "resp.headers", "os.environ['K']", "os.environ.get('K')",
    "os.getenv('K')", "resp.json()", "_body(resp)", "str(resp.text)", "resp.text.strip()", "f'a {resp.text}'",
])
def test_each_source_kind_is_found(expr):
    assert _hits(f"def f(resp):\n    print({expr})\n") == {("f", "cli"): 1}


def test_alias_one_assignment_deep():
    assert _hits("def f(resp):\n    x = resp.text\n    print(x)\n") == {("f", "cli"): 1}
    assert _hits("def f(resp):\n    x = resp.text\n    y = x\n    print(y)\n") == {}


@pytest.mark.parametrize("expr", [
    "type(exc).__name__", "exc.__class__.__name__", "len(resp.text)", "resp.status_code", "'fixed text'",
    "append_failure_status(exc)", "_registry_reason(exc)", "resp.status_code == 200", "exc.status", "type(exc)",
    "exc == 'a'", "resp.text == 'a'",
])
def test_safe_shapes_are_not_findings(expr):
    src = f"def f(resp):\n    try:\n        pass\n    except Exception as exc:\n        print({expr})\n"
    assert _hits(src) == {}


def test_floors_are_pinned():
    # lowering a floor blinds the lint without failing anything else: the values are pinned here
    found, nfiles, nsinks, _ = scan_repo()
    assert MIN_FILES >= 100 and MIN_SINKS >= 600
    assert nfiles >= MIN_FILES + 20 and nsinks >= MIN_SINKS + 100   # headroom: a floor far below the scan is no floor


@pytest.mark.parametrize("body", [
    "a, b = resp.text, 1\n    print(a)",
    "a, b = resp.text\n    print(b)",
    "(a, b) = (1, resp.text)\n    print(b)",
    "m = ''\n    m += resp.text\n    print(m)",
    "if (w := resp.text):\n        print(w)",
    "x: str = resp.text\n    print(x)",
    "m = 'a{}'.format(resp.text)\n    print(m)",
    "m = resp.text.split(',')\n    print(m)",
])
def test_assignment_shapes_carry_taint(body):
    assert _hits(f"def f(resp):\n    {body}\n") == {("f", "cli"): 1}


@pytest.mark.parametrize("body", [
    "a, b = resp.text, 1\n    print(b)",
    "a, b = 1, resp.text\n    print(a)",
    "m = 0\n    m += len(resp.text)\n    print(m)",
    "k = resp\n    print(k.status_code)",
])
def test_assignment_shapes_do_not_over_taint(body):
    assert _hits(f"def f(resp):\n    {body}\n") == {}


def test_dunder_name_is_safe_on_an_alias():
    src = "def f():\n    try:\n        pass\n    except Exception as exc:\n        k = exc\n        print(k.__name__)\n"
    assert _hits(src) == {}


def test_sinks_are_counted_even_when_clean():
    assert scan_source("def f():\n    print('a')\n    print('b')\n")[1] == 2


# --- allowlist rules -----------------------------------------------------------------------------------------------
KEY = "services/x/src/x/a.py::f::cli"


def _list(*lines: str) -> dict[str, tuple[int, str]]:
    return parse_allowlist("\n".join(lines))


def test_allow_must_equal_scan_both_ways():
    allow = _list(f"{KEY} = 2 | allow | operator terminal")
    files = {"services/x/src/x/a.py"}
    assert problems(Counter({KEY: 2}), allow, files) == ([], [])
    assert "new site" in problems(Counter({KEY: 2, KEY + "2": 1}), allow, files)[0][0]
    assert "count changed" in problems(Counter({KEY: 3}), allow, files)[0][0]
    assert "count changed" in problems(Counter({KEY: 1}), allow, files)[0][0]
    assert "stale entry" in problems(Counter(), allow, files)[0][0]


def test_entry_for_absent_file_is_skipped():
    allow = _list(f"{KEY} = 1 | allow | reason")
    assert problems(Counter(), allow, set()) == ([], [])


def test_pending_may_fall_never_rise_and_warns_at_zero():
    allow = _list(f"{KEY} = 2 | pending-7 | PR 7 fixes it")
    files = {"services/x/src/x/a.py"}
    assert problems(Counter({KEY: 2}), allow, files) == ([], [])
    assert problems(Counter({KEY: 1}), allow, files) == ([], [])
    bad, warn = problems(Counter({KEY: 3}), allow, files)
    assert "rose" in bad[0]
    bad, warn = problems(Counter(), allow, files)
    assert bad == [] and "pending-7" in warn[0]


@pytest.mark.parametrize("text", [
    f"{KEY} = 1 | allow",
    f"{KEY} = 1 | allow | ",
    f"{KEY} = x | allow | r",
    f"{KEY} = 1 | maybe | r",
    f"{KEY} = 1 | pending- | r",
    f"{KEY} = 1 | allow | r\n{KEY} = 1 | allow | r",
])
def test_malformed_allowlist_fails(text):
    with pytest.raises(ValueError):
        parse_allowlist(text)


def test_unparsable_file_is_named(tmp_path, monkeypatch):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "bad.py").write_text("def (:\n")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    _, nfiles, _, bad = scan_repo()
    assert bad == ["tools/bad.py"] and nfiles == 0


def test_allowlist_has_a_reason_on_every_line():
    for raw in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        if raw.strip() and not raw.startswith("#"):
            assert raw.count("|") >= 2 and raw.split("|", 2)[2].strip()


if __name__ == "__main__":   # `python test_boundary_echo_lint_c505.py` prints the scan, for building the allowlist
    found, nfiles, nsinks, bad = scan_repo()
    print(f"files {nfiles}, sinks {nsinks}, findings {sum(found.values())} in {len(found)} keys, unparsable {bad}")
    for k in sorted(found):
        print(f"{k} = {found[k]}")
