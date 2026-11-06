# builder-6: rebuild of PR 355 (condition 1)
Old PR 355 (head 640e1bd1, CONFLICTING; reviewer-6 PASS WITH CONDITIONS: rebuild on main, conflict at the tail of test_operator_auth_format2.py) -> new PR 830 https://github.com/SpinStateLabs/field-platform/pull/830, head c9125467e385668dfb837f2f4a56ffc198e7a959, base main ede21674. Old head not pushed.
3 test commits cherry-picked in order; one conflict (both sides appended at the tail of test_operator_auth_format2.py) resolved keeping both, main's block first, 355's unchanged, no duplicate names. test_rotation_events_r2.py clean. Author+committer Don Hagell noreply on all 3. Tests only, nothing under .github/.
Ran (PYTHONUTF8=1): the two files 252 passed; whole field-core suite 1635 passed, 2 skipped. Not run: CI, GX10. Review requested.
