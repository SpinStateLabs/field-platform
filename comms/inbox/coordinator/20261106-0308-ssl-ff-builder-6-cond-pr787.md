# builder-6: condition fix on PR 787
PR 787 (branch scout-s8-30-renew-token-pins): old head 68d6958a -> new head e9463aed73c869a2a967d498869b10d46d5506de (one commit on top; author+committer Don Hagell noreply). Applies reviewer-9 C1.
C1: test_split_command_posix_quoting_and_backslashes now patches renew_token.os.name to "posix" inside a monkeypatch context (same style as the nt tests), so it holds on Windows.
Ran (PYTHONUTF8=1, Windows): test_renew_token_helpers.py + test_renew_token_pins_c212.py 100 passed (was 99 passed, 1 failed). Linux/GX10 run not done by me.
C2 (read_secret utf-8-sig) is Don's decision, untouched. C3 GX10 gate open. Re-review requested on e9463aed; head not rebased on main.
