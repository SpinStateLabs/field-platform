"""Lane 10 probe (C-688): PR 331 `parse_anchors` and `verify_anchors` against the old parser (main). Made-up hashes. Differential and boundary cases."""
import json, os, sys, subprocess, glob, tempfile, importlib.util
R = "/tmp/pr331"
sys.path[:0] = glob.glob(R + "/packages/*/src") + glob.glob(R + "/services/*/src")
from sealed_ledger import anchors as new
old_text = subprocess.run(["git", "show", "origin/main:services/sealed-ledger/src/sealed_ledger/anchors.py"], capture_output=True, text=True, cwd=R).stdout
spec = importlib.util.spec_from_loader("old_anchors", loader=None); old = importlib.util.module_from_spec(spec); old.__dict__["__name__"] = "old_anchors"
import types
# the old module only needs AnchorRecord and load_anchors: reuse the new AnchorRecord, take the old parsing expression
def old_parse(raw):
    return [new.AnchorRecord.model_validate(json.loads(line)) for line in raw.decode("utf-8").splitlines() if line.strip()]
def line(pos, h="a" * 64, **kw):
    d = {"anchored_at": "2026-01-01T00:00:00Z", "chain_length": pos, "head_hash": h}; d.update(kw); return json.dumps(d)
BOM = b"\xef\xbb\xbf"
cases = {
 "one record": line(1).encode() + b"\n",
 "no trailing newline": line(1).encode(),
 "CRLF": (line(1) + "\r\n" + line(2) + "\r\n").encode(),
 "lone CR separators": (line(1) + "\r" + line(2) + "\r").encode(),
 "blank lines between": (line(1) + "\n\n\n" + line(2) + "\n").encode(),
 "whitespace-only line": (line(1) + "\n   \t\n" + line(2)).encode(),
 "empty file": b"", "newline only": b"\n", "only a BOM": BOM, "BOM then newline": BOM + b"\n",
 "BOM + record": BOM + line(1).encode() + b"\n", "two BOMs": BOM + BOM + line(1).encode(),
 "BOM on the second line only": line(1).encode() + b"\n" + BOM + line(2).encode() + b"\n",
 "BOM then CRLF record": BOM + (line(1) + "\r\n").encode(),
 "UTF-16 LE with BOM": (b"\xff\xfe" + line(1).encode("utf-16-le")), "UTF-16 BE with BOM": (b"\xfe\xff" + line(1).encode("utf-16-be")),
 "UTF-8 invalid byte": line(1).encode() + b"\n\xff\n", "latin-1 byte in a string": b'{"anchored_at":"\xe9","chain_length":1,"head_hash":"' + b"a" * 64 + b'"}\n',
 "truncated last line": line(1).encode() + b"\n" + line(2).encode()[:-5],
 "truncated mid-key": line(1).encode() + b"\n" + b'{"anchored_at":"2026',
 "garbage line": line(1).encode() + b"\nnot json\n",
 "two records on one line": (line(1) + " " + line(2) + "\n").encode(),
 "trailing comma / array": b"[" + line(1).encode() + b"]\n",
 "unknown field (extra forbid)": line(1, extra=1).encode(),
 "missing field": b'{"chain_length":1}\n',
 "negative chain_length": line(-1).encode(), "huge chain_length": line(10**30).encode(), "float chain_length": line(1.5).encode(),
 "string chain_length": b'{"anchored_at":"x","chain_length":"3","head_hash":"' + b"a" * 64 + b'"}\n',
 "U+2028 inside a string value": ('{"anchored_at":"a b","chain_length":1,"head_hash":"' + "a" * 64 + '"}\n').encode(),
 "U+0085 (NEL) between records": (line(1) + "\u0085" + line(2) + "\n").encode(),
 "vertical tab / form feed between": (line(1) + "\x0b" + line(2) + "\x0c" + line(3)).encode(),
 "NUL byte": line(1).encode() + b"\x00\n",
 "BOM-prefixed second BOM in text (U+FEFF zero-width inside string)": ('{"anchored_at":"a﻿b","chain_length":1,"head_hash":"' + "a" * 64 + '"}\n').encode(),
}
def run(fn, raw):
    try: return ("ok", len(fn(raw)))
    except Exception as e: return ("err", type(e).__name__)
print(f"{'case':58} {'old':20} {'new':20} note")
diffs = 0
for k, raw in cases.items():
    o, n = run(old_parse, raw), run(new.parse_anchors, raw)
    d = o != n; diffs += d
    print(f"{k:58} {str(o):20} {str(n):20} {'<-- differs' if d else ''}")
print("differences:", diffs)
print("\n== verify_anchors (needs a ledger head; boundary behaviour of order / min-anchors / duplicates) via the module's pure checks")
import inspect
sig = inspect.signature(new.verify_anchors); print("verify_anchors signature:", sig)
