# estate-deployer: Fly Stage 4a LOG-ONLY ARMED (Don: "Allow it")

2026-11-06 ~08:50Z. `f4a-3 arm` DONE from the patched copy: REGISTRY secret + four FIELD_OPERATOR_KEY_<SVC>; REQUIRE unset. After-checks (script, HIGH): names four+REGISTRY, /proc/1/environ count 0, identities on registry/delegation/killswitch/lifecycle, registry set/require unset in 13/13, /health log-only 8/8, sha16 b885ebdab2948f13, 11 rows, file 0600/0700. Mine (estate_probe in machine): health 37/37, continuity 3/3 vs pin 664/1645215d0770cced; drop counters 0/0 on all eight.
Image still main-3804d0b (v18). Local secrets file deleted.
Patch added: `</dev/null` on fly calls in f4lib.sh (fly ssh was consuming the go-sentence stdin: first attempt refused "does not match", nothing changed).
Fly window: 7 polls / ~1 h running with auto-rollback (`f4a-3 rollback --also-identities --live`) on any drop rise.
Owed to Don: f4a-4 V1 (his key), V2 (console kill), V4 (portal headers). Rollback and disarm lines as in the previous report.
