import json, tempfile, pathlib
from sealed_ledger.anchors import verify_anchors
from sealed_ledger.store import LedgerStore
tmp = pathlib.Path(tempfile.mkdtemp()); s = LedgerStore(tmp / "events.jsonl")
for i in range(5): s.append(f"test.event.{i}", {"i": i})
snap = s.snapshot(); N = snap.global_length
H = {i: snap.hash_at(i) for i in range(N)}
def line(pos, h): return json.dumps({"anchored_at": "2026-01-01T00:00:00+00:00", "chain_length": pos, "head_hash": h})
def run(name, lines, **kw):
    p = tmp / "a.jsonl"; p.write_bytes(("\n".join(lines) + "\n").encode()); r = verify_anchors(s, p, **kw)
    print(f"{name:62} ok={r.ok!s:5} checked={r.anchors_checked} distinct={getattr(r,'distinct_positions',None)} {('| ' + (r.first_failure or '')[:70]) if not r.ok else ''}")
run("honest: positions 2 and 5", [line(2, H[1]), line(5, H[4])])
run("honest + idle re-anchor (same position, same hash)", [line(2, H[1]), line(2, H[1]), line(5, H[4])])
run("out of order", [line(5, H[4]), line(2, H[1])])
run("same position, different hashes", [line(2, H[1]), line(2, H[2])])
run("min_anchors=3 with 2 distinct", [line(2, H[1]), line(5, H[4])], min_anchors=3)
run("min_anchors=2 with a repeat counting once", [line(2, H[1]), line(2, H[1])], min_anchors=2)
run("min_anchors=0 (programmatic)", [line(2, H[1])], min_anchors=0)
run("newest anchors removed (prefix only), no floor", [line(2, H[1])])
run("genesis anchor (chain_length 0) with ANY head hash", [line(0, "f" * 64), line(2, H[1])])
run("negative chain_length -1 (index -2 wraps?)", [line(-1, H[N - 2]), line(2, H[1])])
run("negative chain_length -3", [line(-3, H[N - 4])])
run("chain_length beyond the chain", [line(N + 1, "a" * 64)])
run("string chain_length coerced", ['{"anchored_at":"x","chain_length":"2","head_hash":"%s"}' % H[1]])
run("head hash with upper-case hex", [line(2, H[1].upper())])
run("head hash with trailing space", [line(2, H[1] + " ")])
run("empty file", [])
run("BOM only", ["﻿"])
run("BOM + honest record", ["﻿" + line(2, H[1])])
