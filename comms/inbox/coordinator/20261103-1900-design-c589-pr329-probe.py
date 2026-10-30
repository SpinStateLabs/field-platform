import importlib.util, sys
s = importlib.util.spec_from_file_location("chk", "/tmp/pr329/tools/tests/test_compose_static_pins.py"); m = importlib.util.module_from_spec(s); sys.modules["chk"] = m; s.loader.exec_module(m)
m.READ_ONLY_EXEMPT.clear()
f = m._binds_forbidden_host_path
R = m.CALLER_KEYS_ROOT
HARD = "    image: x@sha256:" + "a"*64 + "\n    security_opt: [no-new-privileges:true]\n    cap_drop: [ALL]\n    read_only: true\n    tmpfs: [/tmp]\n"
def doc(svc, top=""):
    top = top or ""
    return "services:\n  s:\n" + HARD + svc + "\n" + top
def refused_doc(svc, top=""):
    t = doc(svc, top)
    try: m.check_compose(t, "services: {}\n")
    except AssertionError as e: return "refused (assert)"
    except Exception as e: return f"CRASH {type(e).__name__}"
    return False
print("== source strings: spelling classes of the empty-default / replacement rule and neighbours")
S = [  # (kind, source, must_refuse)
 ("volume", "${K:-${J:-}}/x", 1), ("volume", f"${{K:-/x}}${{J:-}}{R}", 1), ("volume", f"$${{K:-}}{R}/x", 1), ("volume", f"${{K:- }}{R}/x", 1),
 ("volume", f"${{K:-\t}}{R}/x", 1), ("volume", f"${{K:?}}{R}/x", 1), ("volume", f"${{K:?msg}}/x", 1), ("volume", f"${{K:+}}{R}/x", 1),
 ("volume", f"${{ K:- }}{R}", 1), ("volume", f"$K{R}/x", 1), ("volume", f"${{К:-}}{R}/x", 1),   # Cyrillic K
 ("volume", f"${{K:-{R}}}/x/${{J:-}}", 1), ("volume", f"${{K:-{R}}}/${{J:+/..}}", 1), ("volume", f"${{K:-{R}}}/${{J:-..}}/x", 1),
 ("volume", f"${{K:-{R}/..}}/x", 1), ("volume", f"${{K:-{R}}}/..", 1), ("volume", f"${{K:-{R}}}/../x", 1), ("volume", f"${{K:-{R}}}/.", 1),
 ("volume", f"${{K:-{R}}}", 1), ("volume", f"${{K:-{R}}}/", 1), ("volume", f"${{K:-{R}}}/registry", 0), ("volume", f"${{K:={R}}}/registry", 0),
 ("volume", f"${{K:-{R}}}/${{J:-sub}}", 0), ("volume", "${FIELD_OPERATORS_DIR:-./operators}", 0),
 ("build-context", "github.com/x/y", 1), ("build-context", "github.com/x/y.git#main", 1), ("build-context", "git@host:r", 1), ("build-context", "../../services/x", 0),
 ("build-context", "https://x.invalid/r.git", 1), ("build-context", "/", 1), ("build-context", "docker-image://x", 1),
 ("file", "github.com/x/y", 0),
 ("image-context", "docker-image://x@sha256:" + "a"*64, 0),
]
bad = 0
for kind, src, want in S:
    got = bool(f(src, kind)); ok = got == bool(want); bad += not ok
    if not ok: print("MISS", kind, repr(src), "refused" if got else "accepted", "want", "refuse" if want else "accept")
print("source cases", len(S), "misses", bad)
print("== whole documents: keys, values and types the allowlist must still refuse")
D = [
 ("namespace option as list (unhashable)", "    network_mode: [none]\n", ""),
 ("namespace option as dict", "    pid: {a: 1}\n", ""),
 ("network_mode bridge", "    network_mode: bridge\n", ""),
 ("network_mode empty string", "    network_mode: ''\n", ""),
 ("pid empty string", "    pid: ''\n", ""),
 ("ipc private", "    ipc: private\n", ""),
 ("privileged string true", "    privileged: 'true'\n", ""),
 ("privileged 1", "    privileged: 1\n", ""),
 ("devices empty string", "    devices: ''\n", ""),
 ("devices list nonempty", "    devices: ['/dev/kvm']\n", ""),
 ("cap_add as string", "    cap_add: SYS_ADMIN\n", ""),
 ("cap_add allowed default", "    cap_add: [DAC_READ_SEARCH]\n", None),
 ("cap_add lowercase", "    cap_add: [sys_admin]\n", ""),
 ("cap_add CAP_ prefix", "    cap_add: [CAP_SYS_ADMIN]\n", ""),
 ("ports all interfaces", "    ports: ['0.0.0.0:22:22']\n", None),
 ("build string context github", "    build: github.com/x/y\n", ""),
 ("build dict context github", "    build: {context: github.com/x/y}\n", ""),
 ("build context with query", "    build: {context: '../..?x=1'}\n", None),
 ("build.args path-like", "    build: {context: ., args: {P: /etc}}\n", None),
 ("env_file inside repo", "    env_file: ./app.env\n", None),
 ("env_file dotenv", "    env_file: ./.env\n", ""),
 ("secrets service long, file top", "    secrets: [{source: k, target: x}]\n", "secrets:\n  k:\n    file: ../../.git/config\n"),
 ("top-level x- key", "", "x-foo: {a: 1}\n"),
 ("top-level include list of dict", "", "include:\n  - path: ./other.yml\n"),
 ("top-level include string", "", "include: ./other.yml\n"),
 ("service x- key with host path", "    x-mount: /etc\n", None),
 ("healthcheck with volume-like cmd", "    healthcheck: {test: [CMD, true]}\n", None),
 ("volumes tmpfs long type", "    volumes:\n      - {type: tmpfs, target: /x}\n", None),
 ("volumes type npipe", "    volumes:\n      - {type: npipe, source: //./pipe/docker_engine, target: /x}\n", ""),
 ("volumes type cluster", "    volumes:\n      - {type: cluster, source: x, target: /x}\n", None),
 ("volumes bind with only target", "    volumes:\n      - {type: bind, target: /x}\n", ""),
 ("volumes bind source is a list", "    volumes:\n      - {type: bind, source: ['/etc'], target: /x}\n", ""),
 ("volumes bind source is int", "    volumes:\n      - {type: bind, source: 0, target: /x}\n", ""),
 ("volumes short with 4 colons", "    volumes:\n      - /etc:/x:ro:z\n", ""),
 ("top-level volumes device list", "    volumes: [v:/x]\n", "volumes:\n  v:\n    driver_opts: {type: none, o: bind, device: ['/etc']}\n"),
 ("top-level volumes driver_opts int", "    volumes: [v:/x]\n", "volumes:\n  v:\n    driver_opts: {type: none, o: bind, device: 0}\n"),
 ("top-level volumes external name host path", "    volumes: [v:/x]\n", "volumes:\n  v:\n    external: true\n    name: /etc\n"),
 ("named volume name with slash (service)", "    volumes: ['a/b:/x']\n", ""),
]
for name, svc, top in D:
    r = refused_doc(svc, top or "")
    flag = ""
    if top is None: flag = "(control: expected accept)" if not r else "  <- refused a control?"
    elif not r: flag = "   <-- ACCEPTED (miss)"
    elif isinstance(r, str) and r.startswith("CRASH"): flag = "   <-- crashes instead of refusing"
    print(f"{('refused' if r else 'accepted'):9} {name:46} {flag}")
