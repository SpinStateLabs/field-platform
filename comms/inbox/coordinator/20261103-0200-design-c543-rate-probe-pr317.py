import sys, importlib.util
sys.path[:0] = ["/tmp/pr317/services/attestation-reporter/src", "/tmp/pr317/packages/field-core/src"]
from attestation_reporter.engine import conformance_percent as f
from decimal import Decimal as D, ROUND_HALF_UP
def ref(a, t): return float((D(100) * D(a) / D(t)).quantize(D("0.1"), rounding=ROUND_HALF_UP)) if t else None
bad = 0
cases = [(1,16),(3,16),(5,16),(7,16),(1,8),(1,40),(1,80),(1,160),(1,3),(2,3),(0,5),(5,5),(0,0),(7,0),(1,1),(999999,1000000),(1,32),(2**62, 2**62+1),(10**30, 10**30+3)]
for a,t in cases:
    got = f(a,t); exp = ref(a,t); ok = got == exp; bad += not ok
    print("ok  " if ok else "MISS", a, t, got, "old round():", (round(100*a/t,1) if t else None))
# every tie k/16 and k/80 for k in range, and a sweep of all a<=t<=200 against the exact reference
mism = [(a,t) for t in range(1,201) for a in range(0,t+1) if f(a,t) != ref(a,t)]
print("sweep a<=t<=200 mismatches vs exact half-up:", len(mism))
ties = [(a,t) for t in range(1,201) for a in range(0,t+1) if (D(1000)*a/t) % 1 == D('0.5')]
print("exact ties in sweep:", len(ties), "| old float round() differs from half-up on:", sum(1 for a,t in ties if round(100*a/t,1) != ref(a,t)))
for label, args in {"negative a": (-1,16), "negative total": (1,-16), "a>total": (3,2), "bool": (True, 16), "float a": (1.5, 16), "str": ("1", 16), "None total": (1, None)}.items():
    try: print(label, "->", f(*args))
    except Exception as e: print(label, "-> raises", type(e).__name__)
import json; print("json of result:", json.dumps({"v": f(1,16)}), json.dumps({"v": f(1,3)}))
print("misses", bad)
