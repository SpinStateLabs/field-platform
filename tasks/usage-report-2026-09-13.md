# Sub-agent usage report — session c1a86b9f-4735-49c3-a93f-e1d33b74e4ee

Generated 2026-09-13T09:25:09-04:00 from the agent transcripts (assistant messages de-duplicated by id). Token counts are API-reported. 'Processed input' = uncached input + cache writes + cache reads; cache reads are billed at a fraction of normal input. Agent-hours = sum of each agent's first-to-last message time.

| Started (UTC) | Workflow | Agents | Model(s) | Output tokens | Cache writes | Cache reads | Uncached input | API calls | Tool calls | Wall h | Agent-h |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-12 10:09 | verify-state-block-and-windows-report (wf_3c2214a9-593) | 6 | claude-fable-5-1 | 200 k | 798 k | 10.64 M | 3 k | 87 | 131 | 0.3 | 0.9 |
| 2026-09-12 12:45 | ground-v1-2-closure-plan (wf_885a53c6-0d5) | 13 | claude-fable-5-1 | 697 k | 2.37 M | 74.59 M | 14 k | 453 | 479 | 0.6 | 2.4 |
| 2026-09-12 13:31 | review-v1-2-plan (wf_bc21e4e7-a73) | 6 | claude-fable-5-1 | 301 k | 1.34 M | 33.11 M | 6 k | 179 | 195 | 0.4 | 1.1 |
| 2026-09-12 14:08 | build-phase-a (wf_96783cf5-6f8) | 5 | <synthetic>, claude-fable-5-1 | 86 k | 477 k | 5.88 M | 1 k | 54 | 73 | 0.1 | 0.3 |
| 2026-09-12 14:48 | plain Agent calls | 5 | claude-opus-5 | 299 k | 1.15 M | 47.45 M | 1 k | 258 | 303 | 6.0 | 1.4 |
| 2026-09-12 15:35 | build-phase-b (wf_8750c2bf-5b8) | 6 | claude-opus-5 | 372 k | 1.22 M | 71.36 M | 1 k | 397 | 448 | 1.3 | 1.5 |
| 2026-09-12 19:07 | phase-c-ground-truth (wf_27809387-93c) | 9 | claude-opus-5 | 509 k | 2.60 M | 62.74 M | 1 k | 361 | 432 | 0.6 | 1.8 |
| 2026-09-12 19:19 | deploy-preflight-a-b (wf_184db9e8-57f) | 13 | claude-opus-5 | 785 k | 2.57 M | 95.28 M | 1 k | 554 | 580 | 1.0 | 3.0 |
| 2026-09-12 19:22 | challenge-plan-revision-2 (wf_5cc2aad5-844) | 6 | claude-opus-5 | 357 k | 1.55 M | 57.69 M | 1 k | 300 | 309 | 0.6 | 1.5 |
| 2026-09-12 19:45 | c2-ledger-rotation-design-panel (wf_e107b392-c58) | 7 | claude-opus-5 | 1.61 M | 14.93 M | 396.85 M | 2 k | 962 | 1105 | 6.1 | 11.5 |
| 2026-09-12 22:34 | build-x1-and-c1 (wf_ba0088c5-ba9) | 7 | claude-opus-5 | 791 k | 3.76 M | 156.37 M | 1 k | 567 | 647 | 2.5 | 4.2 |
| 2026-09-12 22:53 | vt-repair-investigation (wf_a1f81b8a-50b) | 4 | claude-opus-5 | 192 k | 650 k | 20.09 M | 0 k | 137 | 154 | 0.5 | 0.7 |
| 2026-09-12 23:29 | build-token-renewal (wf_4c16d8f0-388) | 5 | claude-opus-5 | 782 k | 8.59 M | 108.42 M | 1 k | 348 | 400 | 4.6 | 5.4 |
| 2026-09-13 01:04 | reverify-x1-c1-fixes (wf_83c19ad9-030) | 4 | claude-opus-5 | 188 k | 932 k | 32.06 M | 0 k | 174 | 186 | 0.7 | 1.4 |
| 2026-09-13 02:09 | phase-c-build (wf_dd6baf04-4ab) | 26 | claude-opus-5, claude-sonnet-5 | 2.36 M | 19.77 M | 621.52 M | 4 k | 1876 | 2219 | 10.5 | 18.3 |
| 2026-09-13 04:08 | renewal-hardening (wf_ca83e1fb-6b8) | 9 | claude-opus-5 | 1.15 M | 9.98 M | 224.97 M | 2 k | 755 | 878 | 5.6 | 8.6 |
| 2026-09-13 09:48 | hardening-close-2 (wf_d006eeba-79c) | 10 | claude-opus-5 | 798 k | 4.62 M | 155.45 M | 1 k | 695 | 779 | 2.8 | 5.8 |
| 2026-09-13 12:39 | phase-c-residuals (wf_55369f99-019) | 2 | claude-opus-5 | 146 k | 952 k | 39.05 M | 0 k | 174 | 202 | 0.7 | 0.7 |
| | **All sub-agents** | **143** | <synthetic>, claude-fable-5-1, claude-opus-5, claude-sonnet-5 | **11.62 M** | **78.27 M** | **2213.51 M** | **39 k** | **8331** | **9520** | | **70.4** |

## Main session (the orchestrating conversation)

Model(s) <synthetic>, claude-fable-5-1, claude-opus-5; output 962 k; cache writes 7.09 M; cache reads 340.20 M; uncached input 3 k; 729 API calls; 812 tool calls; 27.9 h since the transcript began.

## Per agent

### verify-state-block-and-windows-report (wf_3c2214a9-593)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| A-source-grounding | claude-fable-5-1 | 25 k | 1.66 M | 15 | 0.10 |
| B-house-style | claude-fable-5-1 | 30 k | 818 k | 19 | 0.10 |
| C-completeness | claude-fable-5-1 | 43 k | 1.84 M | 15 | 0.19 |
| D-remeasure | claude-fable-5-1 | 24 k | 3.51 M | 30 | 0.19 |
| E-docs-semantics | claude-fable-5-1 | 50 k | 2.13 M | 40 | 0.18 |
| critic | claude-fable-5-1 | 27 k | 675 k | 12 | 0.09 |

### ground-v1-2-closure-plan (wf_885a53c6-0d5)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| A-serve-and-wiring | claude-fable-5-1 | 64 k | 9.35 M | 52 | 0.22 |
| B1-B2-delegation | claude-fable-5-1 | 52 k | 7.18 M | 46 | 0.18 |
| B3-killswitch | claude-fable-5-1 | 54 k | 4.01 M | 28 | 0.19 |
| B4-lifecycle-registry-provision | claude-fable-5-1 | 70 k | 8.57 M | 49 | 0.24 |
| C1-C2-ledger | claude-fable-5-1 | 44 k | 3.91 M | 26 | 0.16 |
| C3-replay | claude-fable-5-1 | 44 k | 5.76 M | 40 | 0.16 |
| C4-attestation | claude-fable-5-1 | 47 k | 3.50 M | 26 | 0.17 |
| D1-governor-sentinel-sdk | claude-fable-5-1 | 70 k | 9.13 M | 44 | 0.24 |
| D2-gateway | claude-fable-5-1 | 51 k | 3.58 M | 24 | 0.17 |
| D3-registry-scanner | claude-fable-5-1 | 29 k | 2.21 M | 18 | 0.10 |
| D4-crosswalk-regwatch | claude-fable-5-1 | 38 k | 3.56 M | 26 | 0.14 |
| D5-federation-sdk | claude-fable-5-1 | 30 k | 1.22 M | 35 | 0.10 |
| X-cross-cutting | claude-fable-5-1 | 104 k | 12.61 M | 65 | 0.34 |

### review-v1-2-plan (wf_bc21e4e7-a73)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| A-spec-coverage | claude-fable-5-1 | 35 k | 881 k | 20 | 0.12 |
| B-code-truth | claude-fable-5-1 | 50 k | 9.69 M | 53 | 0.24 |
| C-honesty-line | claude-fable-5-1 | 53 k | 7.50 M | 39 | 0.19 |
| D-sequencing-estates | claude-fable-5-1 | 63 k | 7.32 M | 37 | 0.23 |
| E-designs | claude-fable-5-1 | 52 k | 3.95 M | 25 | 0.20 |
| critic | claude-fable-5-1 | 48 k | 3.77 M | 21 | 0.17 |

### build-phase-a (wf_96783cf5-6f8)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| A0-wiring | <synthetic>, claude-fable-5-1 | 22 k | 1.04 M | 21 | 0.07 |
| A1-lifecycle | <synthetic>, claude-fable-5-1 | 20 k | 1.30 M | 12 | 0.07 |
| A2-attest | <synthetic>, claude-fable-5-1 | 21 k | 2.09 M | 17 | 0.08 |
| A3-crosswalk | claude-fable-5-1 | 23 k | 1.45 M | 23 | 0.07 |
| review | <synthetic> | 0 k | 0 k | 0 | 0.00 |

### plain Agent calls

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| Adversarial review: code and honesty | claude-opus-5 | 40 k | 4.34 M | 41 | 0.16 |
| Adversarial review: wiring, CI, ops | claude-opus-5 | 35 k | 6.09 M | 41 | 0.15 |
| Adversarial security review of Phase B | claude-opus-5 | 81 k | 15.25 M | 78 | 0.47 |
| Adversarial docs/ops review of Phase B | claude-opus-5 | 41 k | 8.72 M | 69 | 0.18 |
| Adversarial review of estate_probe | claude-opus-5 | 102 k | 13.05 M | 74 | 0.42 |

### build-phase-b (wf_8750c2bf-5b8)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| B0 | claude-opus-5 | 40 k | 4.18 M | 46 | 0.14 |
| B1+B2 | claude-opus-5 | 59 k | 11.41 M | 80 | 0.23 |
| B3 | claude-opus-5 | 79 k | 13.95 M | 82 | 0.29 |
| B4 | claude-opus-5 | 108 k | 23.54 M | 116 | 0.43 |
| review:security | claude-opus-5 | 37 k | 7.85 M | 52 | 0.17 |
| review:integration | claude-opus-5 | 49 k | 10.43 M | 72 | 0.22 |

### phase-c-ground-truth (wf_27809387-93c)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| ground:ledger-core | claude-opus-5 | 60 k | 4.96 M | 52 | 0.19 |
| ground:ledger-service | claude-opus-5 | 55 k | 3.86 M | 29 | 0.17 |
| ground:attest | claude-opus-5 | 51 k | 3.42 M | 38 | 0.16 |
| ground:ledger-tests | claude-opus-5 | 76 k | 7.84 M | 64 | 0.29 |
| ground:replay | claude-opus-5 | 44 k | 3.13 M | 36 | 0.15 |
| ground:lifecycle-sweep | claude-opus-5 | 57 k | 6.81 M | 48 | 0.23 |
| ground:consumers | claude-opus-5 | 64 k | 16.70 M | 81 | 0.25 |
| ground:docs-truth | claude-opus-5 | 53 k | 11.05 M | 58 | 0.19 |
| critic:completeness | claude-opus-5 | 48 k | 4.94 M | 26 | 0.20 |

### deploy-preflight-a-b (wf_184db9e8-57f)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| preflight:gb10-compose | claude-opus-5 | 41 k | 5.40 M | 39 | 0.15 |
| preflight:gb10-data | claude-opus-5 | 35 k | 5.31 M | 40 | 0.13 |
| preflight:gb10-live | claude-opus-5 | 32 k | 5.86 M | 44 | 0.13 |
| preflight:fly-config | claude-opus-5 | 42 k | 6.56 M | 47 | 0.18 |
| preflight:images | claude-opus-5 | 78 k | 9.58 M | 59 | 0.37 |
| preflight:risk-walk | claude-opus-5 | 61 k | 10.49 M | 64 | 0.26 |
| preflight:ci-and-git | claude-opus-5 | 26 k | 3.27 M | 30 | 0.09 |
| preflight:rollback | claude-opus-5 | 60 k | 5.50 M | 44 | 0.22 |
| runbook:synthesize | claude-opus-5 | 83 k | 6.26 M | 34 | 0.28 |
| challenge:data-loss | claude-opus-5 | 87 k | 10.26 M | 48 | 0.32 |
| challenge:blast-radius | claude-opus-5 | 69 k | 8.23 M | 43 | 0.26 |
| challenge:ordering | claude-opus-5 | 72 k | 7.47 M | 37 | 0.28 |
| challenge:false-green | claude-opus-5 | 99 k | 11.08 M | 51 | 0.37 |

### challenge-plan-revision-2 (wf_5cc2aad5-844)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| attack:callers-and-blast-radius | claude-opus-5 | 57 k | 12.61 M | 69 | 0.24 |
| attack:fail-closed-cascades | claude-opus-5 | 41 k | 9.67 M | 57 | 0.22 |
| attack:physically-possible | claude-opus-5 | 52 k | 7.84 M | 44 | 0.21 |
| attack:false-green-gates | claude-opus-5 | 63 k | 11.75 M | 55 | 0.25 |
| attack:honesty-and-scope | claude-opus-5 | 53 k | 8.12 M | 42 | 0.21 |
| judge:plan | claude-opus-5 | 93 k | 7.69 M | 42 | 0.35 |

### c2-ledger-rotation-design-panel (wf_e107b392-c58)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| prototype:a-rename-hardened | claude-opus-5 | 248 k | 31.46 M | 116 | 1.59 |
| prototype:b-copy-truncate | claude-opus-5 | 362 k | 89.22 M | 228 | 3.57 |
| prototype:c-new-file-segments | claude-opus-5 | 186 k | 29.25 M | 99 | 1.35 |
| judge:correctness | claude-opus-5 | 266 k | 102.18 M | 228 | 1.45 |
| judge:production-latency | claude-opus-5 | 154 k | 39.77 M | 130 | 1.42 |
| judge:compatibility-and-cost | claude-opus-5 | 156 k | 32.36 M | 106 | 0.97 |
| spec:c2 | claude-opus-5 | 240 k | 72.61 M | 198 | 1.11 |

### build-x1-and-c1 (wf_ba0088c5-ba9)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| build:x1 | claude-opus-5 | 134 k | 31.75 M | 129 | 0.80 |
| build:c1 | claude-opus-5 | 140 k | 22.72 M | 95 | 0.84 |
| review:guards | claude-opus-5 | 111 k | 25.10 M | 102 | 0.51 |
| review:tamper-and-proof | claude-opus-5 | 53 k | 3.88 M | 26 | 0.23 |
| review:secrets-and-roster-safety | claude-opus-5 | 87 k | 10.78 M | 56 | 0.34 |
| review:docs-honesty | claude-opus-5 | 84 k | 17.74 M | 75 | 0.34 |
| fix:all | claude-opus-5 | 183 k | 44.39 M | 164 | 1.12 |

### vt-repair-investigation (wf_a1f81b8a-50b)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| vt:wiring | claude-opus-5 | 32 k | 4.36 M | 36 | 0.13 |
| vt:runtime-safety | claude-opus-5 | 38 k | 4.78 M | 41 | 0.16 |
| vt:authority | claude-opus-5 | 34 k | 5.16 M | 43 | 0.14 |
| vt:plan | claude-opus-5 | 88 k | 5.79 M | 34 | 0.32 |

### build-token-renewal (wf_4c16d8f0-388)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| build:renewal | claude-opus-5 | 243 k | 33.85 M | 109 | 1.74 |
| review:guards | claude-opus-5 | 103 k | 15.31 M | 67 | 0.85 |
| review:secrets-and-false-green | claude-opus-5 | 91 k | 6.99 M | 34 | 0.37 |
| review:crash-and-concurrency | claude-opus-5 | 84 k | 8.83 M | 43 | 0.42 |
| fix:renewal | claude-opus-5 | 262 k | 43.44 M | 147 | 2.02 |

### reverify-x1-c1-fixes (wf_83c19ad9-030)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| reverify:ledger-export | claude-opus-5 | 60 k | 8.46 M | 47 | 0.27 |
| reverify:roster-and-verb | claude-opus-5 | 67 k | 11.63 M | 64 | 0.40 |
| reverify:field-rest-secret | claude-opus-5 | 53 k | 10.08 M | 56 | 0.47 |
| sweep:full | claude-opus-5 | 8 k | 1.89 M | 19 | 0.26 |

### phase-c-build (wf_dd6baf04-4ab)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| build:c2-core | claude-opus-5 | 235 k | 43.30 M | 184 | 1.91 |
| build:c3 | claude-opus-5 | 67 k | 11.79 M | 74 | 0.36 |
| build:c2-ops | claude-opus-5 | 213 k | 51.56 M | 166 | 2.26 |
| build:c4 | claude-opus-5 | 165 k | 33.86 M | 116 | 0.70 |
| build:infra | claude-opus-5 | 183 k | 46.25 M | 162 | 1.09 |
| review:c2-correctness | claude-opus-5 | 114 k | 23.55 M | 73 | 0.78 |
| review:c3-replay | claude-opus-5 | 73 k | 13.72 M | 63 | 0.63 |
| review:c2-perf-deploy | claude-opus-5 | 112 k | 27.27 M | 99 | 0.80 |
| review:infra | claude-opus-5 | 126 k | 32.30 M | 118 | 0.89 |
| review:c4-attest | claude-opus-5 | 98 k | 19.11 M | 82 | 0.87 |
| review:claims | claude-opus-5 | 110 k | 35.86 M | 118 | 0.83 |
| fix:ledger | claude-opus-5 | 238 k | 76.13 M | 193 | 1.71 |
| fix:replay | claude-opus-5 | 106 k | 20.60 M | 97 | 0.55 |
| fix:attest | claude-opus-5 | 134 k | 28.21 M | 122 | 0.85 |
| fix:infra | claude-opus-5 | 186 k | 113.16 M | 268 | 0.91 |
| reverify:ledger | claude-opus-5 | 1 k | 265 k | 2 | 0.01 |
| reverify:sweep | claude-opus-5 | 1 k | 191 k | 2 | 0.01 |
| reverify:infra | claude-opus-5 | 1 k | 274 k | 2 | 0.01 |
| reverify:attest | claude-opus-5 | 1 k | 149 k | 2 | 0.01 |
| reverify:replay | claude-opus-5 | 1 k | 262 k | 3 | 0.01 |
| fix:infra | claude-opus-5 | 6 k | 1.45 M | 9 | 0.03 |
| reverify:ledger | claude-opus-5 | 59 k | 12.41 M | 65 | 0.65 |
| reverify:sweep | claude-sonnet-5 | 20 k | 5.53 M | 51 | 0.95 |
| reverify:replay | claude-opus-5 | 27 k | 4.95 M | 32 | 0.22 |
| reverify:infra | claude-opus-5 | 36 k | 8.65 M | 53 | 0.39 |
| reverify:attest | claude-opus-5 | 43 k | 10.71 M | 63 | 0.86 |

### renewal-hardening (wf_ca83e1fb-6b8)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| fix:sqlite | claude-opus-5 | 129 k | 18.06 M | 105 | 1.44 |
| fix:renewal | claude-opus-5 | 253 k | 60.26 M | 169 | 1.34 |
| verify:renewal-blockers | claude-opus-5 | 149 k | 28.96 M | 89 | 1.08 |
| verify:renewal-new | claude-opus-5 | 110 k | 16.01 M | 75 | 0.62 |
| verify:sqlite-review | claude-opus-5 | 73 k | 13.01 M | 72 | 1.01 |
| close-fix:sqlite | claude-opus-5 | 90 k | 11.15 M | 62 | 0.71 |
| close-verify:sqlite | claude-opus-5 | 48 k | 6.74 M | 44 | 0.29 |
| close-fix:renewal | claude-opus-5 | 209 k | 54.99 M | 186 | 1.49 |
| close-verify:renewal | claude-opus-5 | 89 k | 15.80 M | 76 | 0.62 |

### hardening-close-2 (wf_d006eeba-79c)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| fix:renewal | claude-opus-5 | 107 k | 24.93 M | 100 | 0.55 |
| fix:stores | claude-opus-5 | 163 k | 34.79 M | 155 | 0.91 |
| fix:apis | claude-opus-5 | 50 k | 9.58 M | 63 | 0.35 |
| verify:renewal | claude-opus-5 | 61 k | 10.05 M | 59 | 0.59 |
| verify:stores | claude-opus-5 | 85 k | 16.74 M | 78 | 0.48 |
| verify:apis | claude-opus-5 | 71 k | 15.36 M | 80 | 0.59 |
| close-fix:renewal | claude-opus-5 | 119 k | 20.73 M | 86 | 0.96 |
| close-fix:stores | claude-opus-5 | 61 k | 8.45 M | 67 | 0.60 |
| close-verify:stores | claude-opus-5 | 29 k | 3.74 M | 30 | 0.40 |
| close-verify:renewal | claude-opus-5 | 51 k | 11.08 M | 61 | 0.34 |

### phase-c-residuals (wf_55369f99-019)

| Agent | Model | Output | Cache reads | Tool calls | Hours |
|---|---|---:|---:|---:|---:|
| fix:residuals | claude-opus-5 | 106 k | 27.17 M | 134 | 0.53 |
| verify:residuals | claude-opus-5 | 40 k | 11.88 M | 68 | 0.21 |
