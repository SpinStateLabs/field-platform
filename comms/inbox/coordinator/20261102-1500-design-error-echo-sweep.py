"""Class C sweep: a value from outside the function's trust (response body, exception text, header, environment value)
interpolated into an error message, log line or API reply. AST; non-test code; class+file:line only."""
import ast, pathlib, sys
root = pathlib.Path(sys.argv[1]); out = []
SKIP = ("/tests/", "/test_", "node_modules", "/.git/", "conftest")
LOG = {"debug","info","warning","error","exception","critical","warn"}
def names(n):
    return {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}
def classify(expr, excvars):
    tags = set()
    for x in ast.walk(expr):
        if isinstance(x, ast.Attribute) and x.attr in ("text", "content") and isinstance(x.value, ast.Name) and x.value.id in ("resp","r","response","rev","mresp","cresp","patch","loaded","listing","res","reply"): tags.add("body")
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in ("_body","_text","body_of"): tags.add("body")
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in ("str","repr") and x.args and isinstance(x.args[0], ast.Name) and x.args[0].id in excvars: tags.add("exc")
        if isinstance(x, ast.FormattedValue) and isinstance(x.value, ast.Name) and x.value.id in excvars: tags.add("exc")
        if isinstance(x, ast.Attribute) and x.attr in ("headers",): tags.add("headers")
        if isinstance(x, ast.Attribute) and x.attr == "environ" or (isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "getenv"): tags.add("env")
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "json" and isinstance(x.func.value, ast.Name) and x.func.value.id in ("resp","r","response"): tags.add("json")
    return tags
def interpolates(e):
    return isinstance(e, ast.JoinedStr) or (isinstance(e, ast.BinOp) and isinstance(e.op, (ast.Add, ast.Mod))) or \
           (isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute) and e.func.attr == "format")
for p in sorted(root.rglob("*.py")):
    s = str(p)
    if any(k in s for k in SKIP): continue
    try: tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception: continue
    rel = p.relative_to(root)
    class V(ast.NodeVisitor):
        def __init__(self): self.exc = []
        def visit_ExceptHandler(self, n):
            self.exc.append(n.name); self.generic_visit(n); self.exc.pop()
        def sink(self, kind, node, args):
            ex = {e for e in self.exc if e}
            for a in args:
                t = classify(a, ex)
                if t and (interpolates(a) or isinstance(a, ast.Attribute) or isinstance(a, ast.Call) or isinstance(a, ast.Name)):
                    out.append((str(rel), node.lineno, kind, ",".join(sorted(t)))); return
        def visit_Raise(self, n):
            if isinstance(n.exc, ast.Call): self.sink("raise", n, n.exc.args + [k.value for k in n.exc.keywords])
            self.generic_visit(n)
        def visit_Call(self, n):
            f = n.func
            if isinstance(f, ast.Name) and f.id in ("HTTPException","JSONResponse"):
                self.sink("api-reply", n, n.args + [k.value for k in n.keywords])
            elif isinstance(f, ast.Attribute) and f.attr in LOG and isinstance(f.value, (ast.Name, ast.Attribute)):
                self.sink("log", n, n.args)
            elif isinstance(f, ast.Name) and f.id in ("TransitionStep",) or (isinstance(f, ast.Name) and f.id.endswith("Error")):
                self.sink("error-obj", n, n.args + [k.value for k in n.keywords])
            elif isinstance(f, ast.Attribute) and f.attr == "echo" :
                self.sink("cli-echo", n, n.args)
            self.generic_visit(n)
    V().visit(tree)
from collections import Counter
c = Counter((k, t) for _,_,k,t in out)
print("sites", len(out)); 
for (k,t),n in sorted(c.items()): print(f"  {k:10} {t:14} {n}")
print()
for r in out: print("%s:%d %s %s" % r)
