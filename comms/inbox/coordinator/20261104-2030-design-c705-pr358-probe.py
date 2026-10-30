import sys
from urllib.parse import urlsplit
from field_agent.canary import is_guarded_killswitch_call as g
B = "http://kswitch:8005"
cases = [
 ("exact", B+"/kill/a"), ("revive", B+"/revive/a"), ("drill", B+"/drill/a"),
 ("scheme upper", "HTTP://kswitch:8005/kill/a"), ("host upper", "http://KSWITCH:8005/kill/a"),
 ("trailing dot host", "http://kswitch.:8005/kill/a"), ("userinfo before host", "http://u@kswitch:8005/kill/a"),
 ("userinfo trick @evil", "http://kswitch:8005@evil/kill/a"), ("port longer", "http://kswitch:80050/kill/a"),
 ("port default elided base 80", "http://kswitch/kill/a"), ("lookalike suffix", "http://kswitch:8005.evil/kill/a"),
 ("subdomain suffix", "http://kswitch:8005/.evil/kill/a"), ("dot-dot to read", B+"/kill/../health"),
 ("encoded dot-dot", B+"/kill/%2e%2e/health"), ("encoded slash", B+"/kill%2fa"), ("query", B+"/kill/a?x=1"),
 ("fragment", B+"/kill/a#f"), ("double slash", B+"//kill/a"), ("backslash", B+"/kill\\a"),
 ("tab in path", B+"/kill/a\tb"), ("space", B+"/kill/a b"), ("CRLF", B+"/kill/a\r\nX: y"),
 ("empty tail", B+"/kill/"), ("path only", "/kill/a"),
]
print("base", B)
for label, u in cases:
    try: host = urlsplit(u).hostname; port = urlsplit(u).port
    except ValueError as e: host = port = f"ValueError"
    print(f"{label:28} guarded={g('POST', u, B)!s:5} method=post-lower={g('post', u, B)!s:5} parsed host={host} port={port}")
print("--- other bases")
for b, u in [("http://[::1]:8005","http://[::1]:8005/kill/a"), ("http://[::1]:8005","http://[0:0:0:0:0:0:0:1]:8005/kill/a"),
             ("http://[::1]:8005","http://[::1]:8005@evil/kill/a"), ("http://kswitch:8005/","http://kswitch:8005/kill/a"),
             ("http://kswitch:8005//","http://kswitch:8005/kill/a"), ("","/kill/a"), ("","http://evil/kill/a"), ("http://kswitch:8005/api","http://kswitch:8005/api/kill/a"),
             ("http://kswitch:8005/api","http://kswitch:8005/kill/a"), ("http://kswitch:8005?x=","http://kswitch:8005?x=/kill/a"), ("HTTP://KSWITCH:8005","http://kswitch:8005/kill/a")]:
    print(f"base={b!r:30} url={u!r:48} -> {g('POST', u, b)}")
