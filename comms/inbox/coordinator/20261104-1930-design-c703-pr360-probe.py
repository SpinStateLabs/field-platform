import sys, os, tempfile, pathlib
from datetime import datetime, timezone
for p in ("/tmp/pr360/services/spend-governor/src","/tmp/pr360/packages/field-core/src"): sys.path.insert(0,p)
from fastapi.testclient import TestClient
from spend_governor.api import create_app
from spend_governor.core import GovernorStore, window_start
now = datetime(2026,3,5,13,45,6,123456,tzinfo=timezone.utc)
for per in ("daily","monthly","total","Daily"," daily","daily\n","","weekly","hourly",None,"session"):
    print("window_start", repr(per), window_start(per, now) if per is not None else "TypeError-or-ok", flush=True) if per is not None else print("window_start None ->", window_start(None, now))
c = TestClient(create_app(store=GovernorStore(pathlib.Path(tempfile.mkdtemp())/"s.sqlite3")))
for per in ("daily","daily\n","Daily","weekly","total","monthly\n"):
    r = c.put("/caps/a", json={"agent_id":"a","limit_cents":100,"period":per,"escalate_at_pct":80}); print("PUT /caps period", repr(per), r.status_code)
