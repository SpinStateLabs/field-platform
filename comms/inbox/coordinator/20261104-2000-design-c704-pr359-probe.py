import socket, threading, time, json, sys
sys.path.insert(0, "/tmp/pr359/packages/field-agent/src"); sys.path.insert(0, "/tmp/pr359/packages/field-core/src")
from field_agent import canary, field_client as fc
CAP = canary.MAX_RESPONSE_BYTES
OK = json.dumps({"decision": "ALLOW"}).encode()
def serve(mode, total, drip=None):
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
    def run():
        while True:
            try: c, _ = srv.accept()
            except OSError: return
            try:
                c.recv(65536)
                body = OK + b" " * (total - len(OK))
                if mode == "chunked":
                    c.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Type: application/json\r\n\r\n")
                    for i in range(0, len(body), 4096):
                        ch = body[i:i+4096]; c.sendall(f"{len(ch):x}\r\n".encode() + ch + b"\r\n")
                    c.sendall(b"0\r\n\r\n")
                elif mode == "nolen":      # close-delimited, no Content-Length
                    c.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n"); c.sendall(body)
                elif mode == "drip":
                    c.sendall(b"HTTP/1.0 200 OK\r\n\r\n")
                    for i in range(total):
                        c.sendall(body[i:i+1]); time.sleep(drip)
            except OSError: pass
            finally: c.close()
    threading.Thread(target=run, daemon=True).start(); return f"http://127.0.0.1:{srv.getsockname()[1]}"
def cli(base): return fc.FieldClient(base, "a", "t", timeout=10.0)
for mode in ("chunked", "nolen"):
    for total, label in ((CAP - 1, "cap-1"), (CAP, "cap"), (CAP + 1, "cap+1"), (CAP * 20, "20x cap")):
        base = serve(mode, total)
        fcv = cli(base).check("x").decision
        st, body = canary.urllib_call("POST", base + "/x", {"a": 1}, timeout=5.0)
        print(f"{mode:8} {label:8} FieldClient={fcv:6} canary status={st} body={'too_large' if isinstance(body, dict) and 'response_too_large' in body else body!r}"[:110])
# slow drip: cap patched small; wall clock vs timeout
fc.MAX_RESPONSE_BYTES = 40; canary.MAX_RESPONSE_BYTES = 40
base = serve("drip", 40, drip=0.4)
t0 = time.perf_counter(); st, body = canary.urllib_call("POST", base + "/x", {}, timeout=1.0); t1 = time.perf_counter() - t0
print(f"drip: canary timeout=1.0s, 40 bytes at 0.4s each: returned after {t1:.1f}s status={st}")
base = serve("drip", 40, drip=0.4)
t0 = time.perf_counter(); d = fc.FieldClient(base, "a", "t", timeout=1.0).check("x").decision; print(f"drip: FieldClient timeout=1.0s: returned after {time.perf_counter()-t0:.1f}s decision={d}")
