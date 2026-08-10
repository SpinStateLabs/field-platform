"""Record capstone Scenes 1, 2, 5, assemble Scene 3 from real browser
screenshots, and stitch the full film.

Usage:
  python record_scenes.py scene1|scene2|scene5|scene3|stitch
Scene 3 expects screenshots + captions.json in out/scene3-shots/
(produced by driving the LIVE ops-console; see captions.json schema below).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from recorder_lib import HERE, OUT, Recorder, run

REPO = HERE.parent.parent
DEMO = REPO / "integration" / "demo"


def scene1() -> float:
    r = Recorder("s1", "FIELD Platform — the manifest · Scene 1: declared governance")
    r.title_card("Your AI agents have job descriptions.",
                 "Who enforces them?", 3.5)
    r.caption = ("This is a FIELD manifest — the governance an agent DECLARES: "
                 "its kill switch, its spend cap, its delegated scope.")
    r.type_command("cat integration/demo/manifests/invoicing-agent.yaml")
    text = (DEMO / "manifests" / "invoicing-agent.yaml").read_text(encoding="utf-8")
    pauses = {
        "  kill_switch:": ("A kill switch. Declared.", 2.2),
        "  spend_cap:": ("A five-hundred-dollar daily cap. Declared.", 2.2),
        "delegation:": ("A human grantor, a scope, an expiry. Declared.", 2.2),
    }
    for line in text.splitlines():
        r.rows.append((line, (219, 228, 236)))
        hold = 0.08
        for needle, (caption, t_hold) in pauses.items():
            if line.startswith(needle):
                r.caption = caption
                hold = t_hold
        r.hold(hold)
    r.caption = ("But a declaration is not a control. The FIELD Platform is "
                 "what makes this manifest ENFORCED.")
    r.hold(3.2)
    return r.encode(OUT / "scene1.mp4")


def scene2() -> float:
    r = Recorder("s2", "FIELD Platform — integration demo · Scene 2: one command")
    r.caption = ("One command boots seven governance services and puts a "
                 "deliberately mundane invoicing agent under governance.")
    r.type_command("bash integration/demo/run_demo.sh")
    print("executing run_demo.sh for real (~25 s)…")
    output = run("bash integration/demo/run_demo.sh", cwd=REPO)
    triggers = [
        ("Status: VALID", "Its manifest validates. It is registered to a "
         "HUMAN owner; its spend cap comes straight from the manifest.", 2.4),
        ("token:", "A human mints its authority: a scoped token, expiring "
         "in one hour.", 2.4),
        ("INV-001", "Watch it work — every action checked, every check "
         "written to a tamper-evident ledger, every dollar metered.", 2.0),
        ("ESCALATED", "The fifth draft arrives with the meter at 96% of "
         "cap. It is not blocked — it WAITS FOR A HUMAN.", 3.2),
        ("BLOCKED", "Now the agent tries something it was never granted. "
         "Blocked — citing the exact clause. The function body never "
         "executed.", 3.2),
        ("kill confirmed", "The two-a.m. question — can you stop it? — has "
         "a measured answer.", 3.0),
        ("post-mortem.md", "Incident replay writes the RACI-ready "
         "post-mortem from the ledger alone.", 2.2),
        ("Ledger chain integrity", "It ends at the board: every number "
         "prints the query it came from.", 2.4),
        ("chain intact: True", "Fifteen events. One hash chain. Intact.", 3.0),
    ]
    r.stream_output(output, triggers)
    r.hold(1.5)
    return r.encode(OUT / "scene2.mp4")


def scene3() -> float:
    shots_dir = OUT / "scene3-shots"
    manifest = json.loads((shots_dir / "captions.json").read_text(encoding="utf-8"))
    r = Recorder("s3", "")
    for entry in manifest:  # [{"png": "...", "caption": "...", "seconds": n}]
        r.caption = entry["caption"]
        r.image_still(shots_dir / entry["png"], entry["seconds"])
    return r.encode(OUT / "scene3.mp4")


def scene5() -> float:
    r = Recorder("s5", "FIELD Platform — the honesty line · Scene 5")
    r.caption = ("Every service ships this table: what is enforced in code — "
                 "with the adversarial test that proves it — and what is "
                 "still only declared.")
    r.type_command("sed -n '/## Enforced vs. Declared/,/## LIMITS/p' "
                   "services/sealed-ledger/README.md")
    table = run("sed -n '/## Enforced vs. Declared/,/## LIMITS/p' "
                "services/sealed-ledger/README.md", cwd=REPO)
    for line in table.splitlines():
        r.rows.append((line, (219, 228, 236)))
        r.hold(0.5 if line.startswith("|") else 0.15)
    r.caption = "A governance product that overclaims has already failed."
    r.hold(3.0)

    pack = OUT / "scene3-shots" / "board-pack.png"
    if pack.exists():
        r.caption = ("It ends at the board: a quarterly pack where every "
                     "number prints the query it came from. No number "
                     "without a source.")
        r.image_still(pack, 5.0)

    r.title_card("Declared vs. Enforced",
                 "Twelve governance systems · a dashboard · 168 tests · one "
                 "honest rule — Force Field Protocol · Spin State Labs", 4.5)
    return r.encode(OUT / "scene5.mp4")


def stitch() -> float:
    import imageio_ffmpeg

    parts = ["scene1.mp4", "scene2.mp4", "scene3.mp4", "scene4.mp4", "scene5.mp4"]
    missing = [p for p in parts if not (OUT / p).exists()]
    if missing:
        raise SystemExit(f"missing scene files: {missing}")
    concat = OUT / "concat-film.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat.name,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "capstone.mp4"],
        cwd=OUT, check=True, capture_output=True,
    )
    return 0.0


if __name__ == "__main__":
    which = sys.argv[1]
    seconds = {"scene1": scene1, "scene2": scene2, "scene3": scene3,
               "scene5": scene5, "stitch": stitch}[which]()
    print(f"{which} done ({seconds:.0f}s)" if seconds else f"{which} done")
