S7-26 -> https://github.com/SpinStateLabs/field-platform/pull/751
HIGH: red first (16 of 17 failed on main), element-wise list check + non-string ref guard; GET 200 unavailable, CLI exit 3; 54 retention tests pass. Card item 3 (non-int retention_days) is moot: typed int ge=1 in manifest.py:151.
