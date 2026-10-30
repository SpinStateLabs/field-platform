"""C-541: tests that cannot fail. AST; test functions (name test_*) in test files; file:line + class only."""
import ast, pathlib, sys
from collections import defaultdict
root = pathlib.Path(sys.argv[1]); out = defaultdict(list)
ASSERTISH = {"assert_called", "assert_called_once", "assert_called_with", "assert_called_once_with", "assert_any_call", "assert_not_called", "assert_has_calls"}
def has_assert(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Assert): return True
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if name in ("raises", "warns", "fail", "approx", "assertEqual", "assertTrue", "assertFalse", "assertRaises", "assertIn", "assertIs", "assertIsNone", "assertIsNotNone", "assertGreater", "assertLess", "assertNotEqual", "assertAlmostEqual", "assertCountEqual", "assertRegex", "assertDictEqual", "assertListEqual"): return True
            if name.startswith("assert") or name.startswith("check_") or name.startswith("verify") or name.startswith("expect"): return True
        if isinstance(n, ast.With):
            for it in n.items:
                c = it.context_expr
                if isinstance(c, ast.Call):
                    f = c.func; nm = f.attr if isinstance(f, ast.Attribute) else ""
                    if nm in ("raises", "warns", "assertRaises"): return True
        if isinstance(n, ast.Raise): pass
    return False
def const_true(t):
    return isinstance(t, ast.Constant) and bool(t.value) is True
def tautology(t):
    if const_true(t): return "assert <constant true>"
    if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], (ast.Eq, ast.Is, ast.IsNot, ast.NotEq)):
        if ast.dump(t.left) == ast.dump(t.comparators[0]) and isinstance(t.ops[0], (ast.Eq, ast.Is)): return "assert x == x (same expression both sides)"
    if isinstance(t, ast.Constant): return "assert <constant>"
    if isinstance(t, ast.Tuple) and t.elts: return "assert (tuple) is always true"
    return None
def skips(fn):
    for d in fn.decorator_list:
        s = ast.unparse(d)
        if "skip" in s.lower() and "skipif" not in s.lower():
            reason = [k for k in getattr(d, "keywords", []) if k.arg == "reason"] if isinstance(d, ast.Call) else []
            if not reason and not (isinstance(d, ast.Call) and d.args): return "skip with no reason"
        if "xfail" in s.lower() and not (isinstance(d, ast.Call) and (d.args or any(k.arg == "reason" for k in d.keywords))): return "xfail with no reason"
    return None
def mock_self_assert(fn):
    """assert on the value a Mock was configured to return, in the same function (assert m.return_value == X after m.return_value = X) -- heuristic"""
    cfg = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Attribute) and t.attr in ("return_value", "side_effect"): cfg.add(ast.dump(n.value))
    res = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Assert) and isinstance(n.test, ast.Compare) and len(n.test.comparators) == 1:
            L, Rr = n.test.left, n.test.comparators[0]
            if isinstance(L, ast.Attribute) and L.attr == "return_value" and ast.dump(Rr) in cfg: res.append(n.lineno)
    return res
for p in sorted(root.rglob("test_*.py")) + sorted(root.rglob("*_test.py")):
    s = str(p)
    if any(k in s for k in ("node_modules", "/.git/", "/fixtures/")): continue
    try: tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception: continue
    rel = str(p.relative_to(root))
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")]:
        sk = skips(fn)
        if sk: out[sk].append(f"{rel}:{fn.lineno} {fn.name}")
        if not has_assert(fn):
            # a test that only calls and expects no exception, or only asserts via helper: report as "no assertion"
            body = [b for b in fn.body if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
            out["no assertion, no raises, no helper"].append(f"{rel}:{fn.lineno} {fn.name} ({len(body)} stmts)")
        for n in ast.walk(fn):
            if isinstance(n, ast.Assert):
                t = tautology(n.test)
                if t: out[t].append(f"{rel}:{n.lineno} {fn.name}")
        for ln in mock_self_assert(fn): out["assert on a mock's own configured return_value"].append(f"{rel}:{ln} {fn.name}")
    # module level skips / skipif with no reason
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func; nm = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if nm == "skip" and not n.args and not n.keywords: out["pytest.skip() with no reason"].append(f"{rel}:{n.lineno}")
            if nm == "skipif" and len(n.args) + len(n.keywords) < 2 and not any(k.arg == "reason" for k in n.keywords): out["skipif with no reason"].append(f"{rel}:{n.lineno}")
print("test files scanned under", root)
for k, v in sorted(out.items(), key=lambda kv: -len(kv[1])): print(f"{len(v):5}  {k}")
print()
for k, v in sorted(out.items()):
    print("##", k)
    for x in v[:400]: print(x)
