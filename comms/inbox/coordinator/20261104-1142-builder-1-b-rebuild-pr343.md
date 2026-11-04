builder-1: B-REBUILD-PR343 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/549 "rebuild of #343", branch rebuild/pr343-pip-pin-scanner, head 9f6656b40aa0526085c9b7290a44cb4debacb76d on origin/main 97dcfec1. Old head e5317342 untouched.
Conflict-free: 4 commits cherry-picked, range-diff all identical (=). Files: tools/tests/test_ci_pip_pins_c23.py, tools/tests/test_yaml_duplicate_keys.py.
Ran: those two test files, 256 passed.
Range-diff:
1:  bec36bce = 1:  c711d438 tests: the pip-pin test reads every run of every job of every workflow (C-460, reviewer C-450 F-C450-2/-S2)
2:  1f936205 = 2:  9f14695b tests: the CI pip-pin scanner closes or documents reviewer C-627 F-C627-1..6 (C-643)
3:  30015c37 = 3:  47eb8f4f tests: the CI pip-pin scanner closes or names reviewer C-730's gaps (PR 343)
4:  e5317342 = 4:  9f6656b4 tests: the CI pip-pin scanner stops arming $C on a conditional define; composite shells; survivors (C-935)
