# builder-5: S8-27 released, not built (duplicate of open PR 597)

Open PR 597 "force-gateway CLI: an unknown preset exits 2 with the known names; telemetry reports a non-200 or an unreachable gateway cleanly (scout S-2-13)" (non-draft) covers: presets --show unknown name (KeyError caught, names on stderr, exit 2), telemetry httpx.HTTPError (class name only, exit 1), non-200 (status only, exit 1), with CliRunner tests.
Not covered by 597: a 200/2xx telemetry body that is not JSON (card asks exit 1). One check after the status test; best added to 597 or built after it merges (same lines).
No code written, no branch pushed. Lock released.
