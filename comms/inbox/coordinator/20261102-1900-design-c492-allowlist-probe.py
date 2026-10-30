import importlib.util, sys
s = importlib.util.spec_from_file_location("chk", "/tmp/pr310/tools/tests/test_compose_static_pins.py"); m = importlib.util.module_from_spec(s); sys.modules["chk"] = m; s.loader.exec_module(m)
A = "/home/spinner/.field-local/caller-keys"
f = m._binds_forbidden_host_path
# (kind, source, must_refuse)
T = [
 ("volume", f"{A}", 1), ("volume", f"{A}/", 1), ("volume", f"{A}/registry", 0), ("volume", f"{A}/../.ssh", 1), ("volume", f"{A}/..", 1),
 ("volume", f"{A}-evil/x", 1), ("volume", f"{A}x/y", 1), ("volume", f"//{A}/x", 0), ("volume", f"{A}/./a/../b", 0),
 ("volume", f"${{K:-{A}}}/registry", 0), ("volume", f"${{K:-/etc}}/registry", 1), ("volume", f"${{K:-{A}}}/../../.ssh", 1),
 ("volume", f"${{K:-{A}/..}}/.ssh", 1), ("volume", f"${{K:+{A}}}/registry", 1),   # unset -> "/registry"
 ("volume", f"${{K+{A}}}/registry", 1), ("volume", f"${{K:={A}}}/registry", 0), ("volume", f"${{K=/x}}/registry", 1),
 ("volume", f"${{K:?}}{A}", 1), ("volume", f"${{K-}}{A}/x", 1), ("volume", f"${{K:-}}/etc", 1), ("volume", f"${{K:-}}{A}/x", 1),
 ("volume", "${K:-${J:-/etc}}/x", 1), ("volume", f"${{K:-${{J:-{A}}}}}/x", 0),
 ("volume", "./operators", 0), ("volume", "../../manifests", 0), ("volume", "../../.git", 1), ("volume", "../../..", 1),
 ("volume", "./a/../../../x", 1), ("volume", "./operators/../../../..", 1), ("volume", "./.env", 1), ("volume", "./.env.local", 1),
 ("volume", "./sub/.env", 1), ("volume", "./.git/config", 1), ("volume", "./.GIT", 1), ("volume", "./.ENV", 1),
 ("volume", "./Caddyfile", 0), ("volume", "named_vol", 0), ("volume", "a/b", 1), ("volume", "-x", 1), ("volume", "_x", 1),
 ("volume", "a b", 1), ("volume", "a\tb", 1), ("volume", "", 1), ("volume", " /etc ", 1), ("volume", "/etc\x00", 1),
 ("volume", "docker-image://x", 1), ("volume", "https://x/y", 1), ("volume", "git@host:repo", 1), ("volume", "C:\\x", 1),
 ("file", "/etc/shadow", 1), ("file", "secret.txt", 0), ("file", "../../.env", 1), ("file", "../../..", 1), ("file", ".env", 1),
 ("file", f"{A}/k", 0), ("file", "~/.ssh/id", 1), ("file", "${X}", 1), ("file", "./a b", 0),
 ("build-context", ".", 0), ("build-context", "../..", 0), ("build-context", "../../..", 1), ("build-context", "/", 1), ("build-context", "https://x/r.git", 1),
 ("build-context", "../../.git", 1), ("build-context", "../../services/x", 0),
 ("image-context", "docker-image://x@sha256:"+"a"*64, 0), ("image-context", "docker-image://${X}", 1),
]
bad = 0
for kind, src, want in T:
    got = bool(f(src, kind)); ok = got == bool(want); bad += not ok
    if not ok: print("MISS", kind, repr(src), "refused" if got else "accepted", "want", "refuse" if want else "accept")
print("cases", len(T), "misses", bad)
