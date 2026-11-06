# Stage 0 deploy record: TEMPLATE (Phase G, G16)

A template for the record the coordinator or estate-deployer writes OUTSIDE this repository's public history after a
Stage 0 deploy. It holds no estate fact: every value below is a blank to fill. Never put an address, a key, a key hash,
a secret or a build id of a live estate into a public file.

## Record

- Estate: `<name>`
- Date (UTC): `<yyyy-mm-dd hh:mm>`
- Image build id: `<first 12 hex of the commit>` (all eight operator-block services report the same one)
- Operator flags: all off as seen from `/health` (`operator_mode` off, no identity, in all eight services)
- Check run: `python tools/phase_g_stage0_check.py --base <base> --expect-build-sha <full commit id>`, exit `<0|1>`,
  `<N/N checks passed>`
- Rollback reference: `<previous image build id, first 12 hex>`
- Not done at this stage: no operators file installed, no arming, no go sentence.

## Reading the check

`tools/phase_g_stage0_check.py` reads only `GET /health` of the eight operator-block services. It passes when every one
answers as itself, reports one build id (the expected one, when given) and shows `operator_mode` off, `identity_present`
false and no identity id. It shows that the flags behave off, which an explicit `FIELD_OPERATOR_REQUIRE=0` with no registry would also
show; it cannot prove a variable is unset, and it proves nothing about estate secrets or files: those are the
deployer's own steps.
