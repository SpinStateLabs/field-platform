"""Lane 10 probe (C-619): spellings the public-safety guard (tools/tests/test_public_safety_c560.py) must flag. Made-up names only
(no real value appears here). A case that is NOT flagged is a miss. Run: GUARD=<checkout>/tools/tests/test_public_safety_c560.py pytest -q"""
import importlib.util, os, sys
import pytest
s = importlib.util.spec_from_file_location("g", os.environ["GUARD"]); g = importlib.util.module_from_spec(s); sys.modules["g"] = g; s.loader.exec_module(g)
N = "zed"                      # made-up account name
CASES = {
 # windows paths
 "C:\\Users\\N": ("C:\\" + "Users\\" + N, 1), "C:/Users/N": ("C:/Users/" + N, 1), "escaped backslashes": ("C:\\\\Users\\\\" + N, 1),
 "lower-case drive and users": ("c:\\users\\" + N, 1), "upper-case USERS": ("C:\\USERS\\" + N, 1), "other drive D:": ("D:\\Users\\" + N, 1),
 "extended-length prefix": ("\\\\?\\C:\\Users\\" + N, 1), "file URL": ("file:///C:/Users/" + N + "/x", 1),
 "percent-encoded": ("C%3A%5CUsers%5C" + N, 1), "WSL mount": ("/mnt/c/Users/" + N, 1), "git-bash style": ("/c/Users/" + N, 1),
 "UNC admin share": ("\\\\host\\c$\\Users\\" + N, 1), "OneDrive path": ("C:\\Users\\" + N + "\\OneDrive\\x", 1), "name with space": ("C:\\Users\\Jane Doe\\x", 1),
 "env expansion not a name (control)": ("%USERPROFILE%\\x", 0),
 # unix
 "/home/N": ("/home/" + N, 1), "/Users/N": ("/Users/" + N, 1), "/var/home/N (immutable distros)": ("/var/home/" + N, 1),
 "/export/home/N": ("/export/home/" + N, 1), "/data/home/N": ("/data/home/" + N, 1), "tilde-user": ("~" + N + "/x", 1),
 "/root (not personal, control)": ("/root/x", 0), "placeholder (control)": ("/home/<home>/x", 0), "generic runner (control)": ("/home/runner/x", 0),
 "/home/UPPER": ("/HOME/" + N, 1),
 # private addresses
 "10/8": ("10.4.5.6", 1), "172.16/12": ("172.20.1.2", 1), "192.168/16": ("192.168.7.8", 1), "CGNAT 100.64/10 (VPN overlay)": ("100.101.102.103", 1),
 "link-local 169.254": ("169.254.9.9", 1), "IPv6 ULA fd": ("fd12:3456:789a::1", 1), "IPv6 ULA fc": ("fc00::1", 1), "IPv6 link-local": ("fe80::1", 1),
 "decimal integer ip": ("167838214", 1), "hex ip": ("0x0a040506", 1), "ip with port": ("10.4.5.6:8080", 1), "ip in url": ("http://192.168.7.8/x", 1),
 "ip followed by dot sentence": ("see 10.4.5.6.", 1), "mDNS host name": ("zedbox.local", 1), "documentation range (control)": ("203.0.113.5", 0), "loopback (control)": ("127.0.0.1", 0),
 # mailboxes
 "gmail": ("zed@gmail.com", 1), "googlemail": ("zed@googlemail.com", 1), "outlook": ("zed@outlook.com", 1), "live.com": ("zed@live.com", 1), "msn": ("zed@msn.com", 1),
 "aol": ("zed@aol.com", 1), "gmx": ("zed@gmx.net", 1), "yandex": ("zed@yandex.ru", 1), "qq": ("zed@qq.com", 1), "me.com": ("zed@me.com", 1), "pm.me": ("zed@pm.me", 1),
 "protonmail": ("zed@protonmail.com", 1), "hey.com": ("zed@hey.com", 1), "fastmail": ("zed@fastmail.com", 1), "zoho": ("zed@zoho.com", 1),
 "mailto link": ("mailto:zed@gmail.com", 1), "obfuscated at/dot": ("zed at gmail dot com", 1), "percent-encoded at": ("zed%40gmail.com", 1), "html entity at": ("zed&#64;gmail.com", 1),
 "parenthesised at": ("zed(at)gmail.com", 1), "git noreply for a person (control)": ("123+zed@users.noreply.github.com", 0), "example domain (control)": ("zed@example.com", 0),
}
@pytest.mark.parametrize("name", sorted(CASES))
def test_flagged(name):
    text, want = CASES[name]
    got = sum(g.scan_text(text).values())
    assert (got >= 1) == bool(want), f"{'NOT flagged' if want else 'flagged'}: {name}"
