B-S5-22 -> https://github.com/SpinStateLabs/field-platform/pull/698
HIGH: red first (7 failed on main), per-agent guard, save_tokens atomic 0600 after each mint, verify guard, assert->ValueError. Overlaps PR 513 (corrupt file/TTL) in main(); job_grantors 14 errors identical on main; POSIX 0600 test skipped here.
