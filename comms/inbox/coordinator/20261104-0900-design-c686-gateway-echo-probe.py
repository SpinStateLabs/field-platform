import os, sys, glob
for sub in glob.glob("/tmp/pr324/packages/*/src")+glob.glob("/tmp/pr324/services/*/src"): sys.path.insert(0, sub)
os.environ["FORCE_GATEWAY_ENFORCE"]="1"; os.environ["FIELD_SENTINEL_URL"]="http://svc-user:MADE-UP-PASS-1234@sentinel.invalid:8004/check?token=MADE-UP-TOKEN"
os.environ.pop("FIELD_SHARED_SECRET", None)
from force_gateway import api
from fastapi.testclient import TestClient
app = api.create_app()
c = TestClient(app)
r = c.get("/health"); body = r.text
print("health status", r.status_code, "| userinfo password in body:", "MADE-UP-PASS" in body, "| query token in body:", "MADE-UP-TOKEN" in body)
# numeric tunables: startup ValueError text
for var in ("FORCE_GATEWAY_SENTINEL_TIMEOUT","FORCE_GATEWAY_LATENCY_BUDGET_MS","FORCE_TELEMETRY_RETAIN","FORCE_GATEWAY_COOLDOWN_S","FORCE_GATEWAY_JUDGE_SAMPLE"):
    os.environ[var] = "MADE-UP-NOT-A-NUMBER"
    try: api.create_app(); print(var, "-> no error")
    except Exception as e:
        print(f"{var:36} -> {type(e).__name__}: marker_in_message={'MADE-UP-NOT-A-NUMBER' in str(e)}")
    finally: os.environ.pop(var, None)
