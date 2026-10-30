import sys, random
from decimal import Decimal, localcontext, ROUND_HALF_UP, getcontext, Inexact, Context
from attestation_reporter.engine import conformance_percent as cp
def exact(a, b):  # independent integer rule: tenths = floor((2000a + b) / (2b))
    return ((2000 * a + b) // (2 * b)) / 10
def near_tie(b, below=True):
    # a such that 1000a/b is just under (or exactly at) a half-tenth boundary: 2000a = (2k+1)b - 1  => needs b odd-compatible
    for k in range(1, 5):
        num = (2*k + 1) * b - (1 if below else 0)
        if num % 2000 == 0: return num // 2000
    return None
print("near ties: 1000a/b = 1.5 -/+ 1/(2b); real function vs independent integer rule, and a float-intermediate mutant")
def mutf(a, b): return float(Decimal(100 * a / b).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
for e in (3, 10, 14, 16, 18, 20, 25, 30, 40, 50, 55, 57, 58, 59, 60, 62, 70):
    row = []
    for label, resid, off in (("below", 667, -1), ("above", 1333, 1)):
        b = (10**e // 2000) * 2000 + resid
        a = (3 * b + off) // 2000
        assert 2000 * a == 3 * b + off and 0 <= a <= b, (e, label)
        got = cp(a, b)
        row.append(f"{label}: real {'ok' if got == exact(a, b) else 'MISMATCH'} float-mutant {'ok' if mutf(a, b) == exact(a, b) else 'WRONG'}")
    print(f"  b~1e{e:<3}", " | ".join(row))
random.seed(1); bad = 0
for _ in range(20000):
    b = random.randint(1, 10**random.randint(1, 40)); a = random.randint(0, b)
    if cp(a, b) != exact(a, b): bad += 1
print("random 20000 pairs up to 1e40: mismatches =", bad)
print("input contract:")
for args in ((0,0),(1,0),(-1,5),(6,5),(True,2),(1,True),(1.0,2),(2,4.0),("1",2),(None,2)):
    try: print(" ", args, "->", cp(*args))
    except Exception as ex: print(" ", args, "->", type(ex).__name__)
import enum
class N(enum.IntEnum): ONE = 1
print("  IntEnum accepted:", cp(N.ONE, 4))
ctx = getcontext(); ctx.traps[Inexact] = True
try: print("  with Inexact trap set, 1/3 ->", cp(1, 3))
except Exception as ex: print("  with Inexact trap set, 1/3 ->", type(ex).__name__)
