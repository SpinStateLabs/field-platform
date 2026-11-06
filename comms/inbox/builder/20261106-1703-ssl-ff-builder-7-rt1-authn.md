# ssl-ff-builder-7: B-RT1-authn-ascii-compare done
PR: https://github.com/SpinStateLabs/field-platform/pull/839, head 524da3594d5d1d85a732ad92efa7bdd93eb3dedb (branch builder7/rt1-authn-ascii), one commit on main, repo identity, nothing under .github/.
authn.py compares bytes (header re-encoded latin-1, secret UTF-8): non-ASCII header is 401 (not 500), /health open, non-ASCII secret handled with one install warning (variable name only). 7 new tests via raw ASGI (test client re-encodes header bytes); restoring the old compare fails 6 of 13; 261 related tests pass. Full suites not run locally.
Review requested on the exact head.
