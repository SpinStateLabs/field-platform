# B-COND-PR503 addendum (the earlier report lost a phrase to shell quoting)
The gateway's call to judge.judge(...) is wrapped in a bare except-Exception clause (services/force-gateway/src/force_gateway/api.py ~684-690); on any failure it counts judge_bypassed with reason error and returns None.
