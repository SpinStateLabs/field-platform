# builder-5: B-REBUILD-PR445 -> draft PR 570
- https://github.com/SpinStateLabs/field-platform/pull/570 rebuilds #445 (old head 307b1cf0). Old PR untouched.
- Clean cherry-pick; range-diff '=' for both commits (no changes beyond rebase). HIGH.
- Test local: test_auth_headers_outside_core_c1149.py 27 passed on rebuilt tree.
- Identity checked on all commits before push.
