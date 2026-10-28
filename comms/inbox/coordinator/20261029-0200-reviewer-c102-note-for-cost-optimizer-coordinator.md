# Note for the cost-optimizer coordinator (relay requested by FIELD coordinator, C-102)

`FieldClient` in SpinStateLabs/cost-optimizer (817aace) has two gaps, proven in field-platform review C-41:
1. `NO_REDIRECT = urllib.request.build_opener(_NoRedirect()).open` keeps urllib's environment ProxyHandler; with `http_proxy`/`HTTPS_PROXY`/`ALL_PROXY` set before import, `x-field-auth` (the shared secret) is sent to the proxy.
2. `resp.read()` is unbounded.
Fix as in field-platform PR 68 (23a1b81, reviewed PASS): `build_opener(urllib.request.ProxyHandler({}), _NoRedirect())`, and `resp.read(MAX_RESPONSE_BYTES + 1)` with the reply refused above the cap. Add a subprocess test that sets the proxy variables before import (the opener is built at import) and a test that sends a reply of exactly the cap and one of cap+1.
Reviewer did not edit that repository.
