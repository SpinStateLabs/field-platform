import sys, os, json, copy, random, importlib.util, tempfile, pathlib
sys.path.insert(0, "/tmp/pr355/packages/field-core/tests"); sys.path.insert(0, "/tmp/pr355/packages/field-core/src")
import test_operator_auth_format2 as T
SRC = open("/tmp/pr355/packages/field-core/src/field_core/operator_auth.py").read()
MUT = SRC.replace("retired[h] = max(generation, retired.get(h, 0))", "retired[h] = generation", 1)
assert MUT != SRC
def load(name, text):
    p = pathlib.Path(tempfile.mkdtemp()) / f"{name}.py"; p.write_text(text)
    spec = importlib.util.spec_from_file_location(f"field_core.{name}", p); m = importlib.util.module_from_spec(spec)
    sys.modules[f"field_core.{name}"] = m; spec.loader.exec_module(m); return m
orig, mut = load("oa_orig", SRC), load("oa_mut", MUT)
def gen_doc(g, k):
    d = copy.deepcopy(T.doc()); d["generation"] = g
    r = T.row(d, "svc-killswitch"); r.pop("next_key", None); r["key_sha256"] = T.h(f"fok_test-ks-{k}-not-a-real-key"); return d
def run(mod, seq, tmp):
    mod._retired_state.clear(); mod._retired_seen.clear()
    p = tmp / "operators.json"; res = []
    for g, k in seq:
        p.write_text(json.dumps(gen_doc(g, k)), encoding="utf-8")
        try: rows = mod.load_registry(str(p)); ks = [r for r in rows if r["operator_id"] == "svc-killswitch"]
        except Exception as e: ks = [type(e).__name__]
        res.append("ok" if ks and ks[0] != "RegistryUnavailable" and isinstance(ks[0], dict) and ks[0].get("status") == "active" else "refused")
    return res
random.seed(7); tmp = pathlib.Path(tempfile.mkdtemp()); found = None
for _ in range(4000):
    seq = [(random.randint(41, 50), random.randint(0, 3)) for _ in range(random.randint(3, 8))]
    a, b = run(orig, seq, tmp), run(mut, seq, tmp)
    if a != b: found = (seq, a, b); break
print("divergence:", found)
