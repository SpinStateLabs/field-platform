import glob, sys, os
from datetime import datetime, timedelta, timezone, date
from claude_approver import core as c
def show(label, v):
    m = c._time_or_none(v)
    print(f"{label:46} parsed={'yes' if m else 'no ':3} aware={None if m is None else (m.tzinfo is not None)!s:5} -> {None if m is None else m.astimezone(timezone.utc).isoformat()}")
now = datetime.now(timezone.utc)
vals = {
 "aware UTC datetime": now, "naive datetime (now)": now.replace(tzinfo=None), "ISO with Z": now.isoformat().replace("+00:00","Z"),
 "ISO +02:00": now.astimezone(timezone(timedelta(hours=2))).isoformat(), "ISO -05:30": now.astimezone(timezone(timedelta(hours=-5,minutes=-30))).isoformat(),
 "date only": now.strftime("%Y-%m-%d"), "basic format 20261104T120000Z": now.strftime("%Y%m%dT%H%M%SZ"), "padded (spaces)": "  " + now.isoformat() + "  ",
 "space separator": now.strftime("%Y-%m-%d %H:%M:%S+00:00"), "year 2999": "2999-01-01T00:00:00Z", "year 9999 max": "9999-12-31T23:59:59Z",
 "year 0001": "0001-01-01T00:00:00Z", "epoch int": 1730000000, "float": 1730000000.5, "bool True": True, "None": None, "empty": "", "NaN text": "nan",
 "unicode digits": "２０２６-１１-０４T00:00:00Z", "offset +24:00": "2026-11-04T00:00:00+24:00", "leap second": "2026-06-30T23:59:60Z", "overflow near max with offset": "9999-12-31T23:59:59-23:00",
}
for k, v in vals.items():
    try: show(k, v)
    except Exception as e: print(f"{k:46} RAISES {type(e).__name__}: {str(e)[:50]}")
print()
# the bound
slack = c.CURSOR_FUTURE_SLACK
print("slack:", slack)
for label, delta in {"now+4m59s": timedelta(minutes=4, seconds=59), "now+5m (boundary)": timedelta(minutes=5), "now+5m01s": timedelta(minutes=5, seconds=1), "now+1y": timedelta(days=365), "now-1y": timedelta(days=-365)}.items():
    m = now + delta; future = m > now + slack
    print(f"{label:22} ignored_as_future={future}")
