# B-COND-PR616-017901f: no push; the conditions are CI and GX10 only

Head stays 017901f0 (tests only, 4 commits). Conditions: CI green, full GX10 16/16 on that head: verification, not builder code.
Follow-ups for B-FU-PR616-*: F1 LOW, three clean/over-flag cases for the lint corpus: `self.stderr.write(resp.text)` / `other.stdout.write(...)` (S4), a logging call with `extra={"detail": resp.text}` (R5), a sink nested in a list or call under `return` (R11).
F2 MEDIUM, not this PR, needs a decision (Don or architect): the force-gateway 503 body returned to a /v1/messages caller carries the sentinel's configured base URL (force_gateway/api.py:567, exc built at :365); the PR lists it as `allow | DEBT`. Fix or keep as DEBT; I would fix it (a fixed text plus the exception class, no URL) as a small builder card, B-FU-gateway-503-no-base-url.
