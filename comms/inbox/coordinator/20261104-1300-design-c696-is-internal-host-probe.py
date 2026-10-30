"""Lane 10 probe (C-696): PR 356 `is_internal_host` and its three stdlib copies. Differential + oracle. Made-up values only."""
import glob, importlib, importlib.util, ipaddress, os, random, socket, sys
R = "/tmp/pr356"
sys.path[:0] = glob.glob(R + "/packages/*/src") + glob.glob(R + "/services/*/src") + [R + "/tools"]
hosts = importlib.import_module("field_core.hosts")
fc = importlib.import_module("field_agent.field_client")
def load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); sys.modules[name] = m
    try: s.loader.exec_module(m); return m
    except Exception as e: print("could not import", name, type(e).__name__, str(e)[:60]); return None
ep = load("estate_probe", R + "/tools/estate_probe.py"); rt = load("renew_token", R + "/tools/renew_token.py")
IMPL = {"field_core.hosts(allow_names=False)": lambda h: hosts.is_internal_host(h, allow_names=False), "field_client": fc._private_host}
if ep: IMPL["estate_probe"] = ep._internal_host
if rt: IMPL["renew_token"] = rt._internal_host
NETS = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7")]
def oracle(h):
    h = (h or "").lower()
    if h == "localhost": return True
    try: ip = ipaddress.ip_address(h)
    except ValueError:
        try: ip = ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(h)))
        except Exception: return False
    if ip.version == 6 and ip.ipv4_mapped is not None: ip = ip.ipv4_mapped
    return any(ip.version == n.version and ip in n for n in NETS)
FIXED = ["localhost", "LOCALHOST", "localhost.", "127.0.0.1", "127.1", "0x7f.1", "0x7f000001", "2130706433", "017700000001", "0177.0.0.1", "10.0.0.1", "10.1", "010.0.0.1", "172.16.0.1", "172.31.255.255", "172.32.0.1", "192.168.1.1", "192.169.0.1",
 "100.64.0.1", "169.254.169.254", "0.0.0.0", "255.255.255.255", "198.18.0.1", "192.0.0.1", "8.8.8.8", "134744072", "0x08080808", "01001001010", "::1", "::", "[::1]", "::ffff:10.0.0.1", "::ffff:8.8.8.8", "::ffff:127.0.0.1", "::ffff:a00:1", "::ffff:808:808",
 "fc00::1", "fd12::1", "fe80::1", "fe80::1%eth0", "::1%eth0", "::1%25eth0", "fd00::1%lo", "2001:4860:4860::8888", "2001:4860:4860::8888%lo", "64:ff9b::a00:1", "64:ff9b::808:808", "2002:a00:1::", "2002:808:808::", "::10.0.0.1", "::127.0.0.1", "::ffff:0:10.0.0.1",
 "10.0.0.1.", "10.0.0.1 ", " 10.0.0.1", "10.0.0.1\n", "10.0.0.1\x00", "１０.0.0.1", "10。0。0。1", "10.0.0.1%", "10.0.0.256", "10.0.0", "10", "0x", "0x.", ".", "..", "", None, "a", "cafe", "dead.beef", "10.0.0.1.evil.test", "evil.test", "x.local", "x.internal", "registry"]
random.seed(356)
def rnd_v4():
    parts = [random.choice([str(random.randint(0, 255)), hex(random.randint(0, 255)), "0" + oct(random.randint(0, 255))[2:], str(random.randint(0, 2**32 - 1))]) for _ in range(random.randint(1, 4))]
    return ".".join(parts)
RAND = [rnd_v4() for _ in range(4000)] + [str(ipaddress.IPv6Address(random.getrandbits(128))) for _ in range(1500)] + ["::ffff:" + str(ipaddress.IPv4Address(random.getrandbits(32))) for _ in range(1500)]
bad_oracle = 0; bad_agree = 0; samples = []
for h in FIXED + RAND:
    res = {}
    for n, f in IMPL.items():
        try: res[n] = bool(f(h))
        except Exception as e: res[n] = f"RAISES {type(e).__name__}"
    vals = set(map(str, res.values()))
    if len(vals) > 1: bad_agree += 1; samples.append(("DISAGREE", h, res))
    o = oracle(h)
    if any(v is not o for v in res.values() if isinstance(v, bool)) : bad_oracle += 1; samples.append(("ORACLE", h, {k: v for k, v in res.items()}, o))
print("inputs", len(FIXED) + len(RAND), "| implementations", list(IMPL), "| disagreements among implementations", bad_agree, "| disagreements with the independent oracle", bad_oracle)
for s in samples[:12]: print(s)
print("--- fixed list verdicts (field_core):")
for h in FIXED:
    try: v = hosts.is_internal_host(h, allow_names=False)
    except Exception as e: v = f"RAISES {type(e).__name__}"
    print(f"  {('ACCEPT' if v is True else 'refuse' if v is False else v):8} {h!r}")
