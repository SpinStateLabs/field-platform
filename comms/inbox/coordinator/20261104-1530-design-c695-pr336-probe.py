import os, sys, threading
for p in ("services/kill-switch/src","packages/field-core/src","services/registry/src","services/sealed-ledger/src"):
    sys.path.insert(0, os.path.abspath(p))
os.environ["HTTP_PROXY"]="http://127.0.0.1:9"; os.environ["ALL_PROXY"]="http://127.0.0.1:9"
from kill_switch import api
c = api.new_endpoint_client()
print("trust_env", c._trust_env, "follow", c.follow_redirects)
print("mounts", len(c._mounts))
print("scrub", api._scrub("fail: http://u:p@h/x and ftp://a"), "|", api._scrub("x"*300).__len__())
