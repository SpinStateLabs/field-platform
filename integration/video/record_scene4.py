"""Render Scene 4 ("Try to cheat it") as a terminal-replay video.

Honesty contract: every command shown is ACTUALLY EXECUTED against freshly
staged assets and every output line in the video is the verbatim captured
output — this is an asciinema-style replay, not a mock-up. Typing animation
and captions are presentation; the bytes are real.

Usage:  python integration/video/record_scene4.py
Output: integration/video/out/scene4.mp4 (1080p30, ~60 s, silent with
        burned-in caption lines from docs/VIDEO-SCRIPT.md)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
S4 = HERE / "scene4"
OUT = HERE / "out"
W, H = 1920, 1080
FPS = 30
MARGIN_X, MARGIN_TOP = 70, 60
LINE_H = 34
FONT_SIZE = 24
CAPTION_SIZE = 30
MAX_ROWS = 24

BG = (13, 17, 22)
FG = (219, 228, 236)
DIM = (125, 139, 153)
GREEN = (63, 185, 107)
RED = (224, 92, 79)
AMBER = (224, 166, 60)
ACCENT = (77, 159, 220)
CAPTION_BG = (23, 30, 38)

FONT = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", FONT_SIZE)
FONT_BOLD = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", FONT_SIZE)
FONT_CAPTION = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", CAPTION_SIZE)
FONT_TITLE = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 54)

PROMPT = "field-platform/scene4 $ "

# Git Bash explicitly — plain "bash" from Windows Python resolves to the
# WSL bash in System32 (HOME=/root, no venv). Discovered the hard way.
BASH = r"D:\Apps\Git\usr\bin\bash.exe"

# bash spawned from Windows Python lacks HOME; the stage script and the
# venv-on-PATH resolution both need it.
_home_win = os.environ.get("USERPROFILE") or os.environ.get("HOME", "")
_home_posix = "/" + _home_win[0].lower() + _home_win[2:].replace("\\", "/")
ENV = {**os.environ, "HOME": _home_posix}
ENV["PATH"] = (str(Path(_home_win) / ".venvs" / "field-platform" / "Scripts")
               + os.pathsep + ENV.get("PATH", ""))


def line_color(text: str):
    if text.startswith("TAMPERED") or "ANCHOR FAILURE" in text:
        return RED
    if text.startswith("OK — "):
        return GREEN
    return FG


class Recorder:
    """Accumulates (image, duration_s) stills for ffmpeg concat."""

    def __init__(self):
        self.stills: list[tuple[Path, float]] = []
        self.frames_dir = OUT / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.rows: list[tuple[str, tuple]] = []  # (text, color)
        self.caption = ""

    def _render(self) -> Image.Image:
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 42], fill=(23, 30, 38))
        d.text((MARGIN_X, 8), "FIELD Platform — sealed-ledger · Scene 4: try to cheat it",
               font=FONT, fill=DIM)
        rows = self.rows[-MAX_ROWS:]
        y = MARGIN_TOP
        for text, color in rows:
            d.text((MARGIN_X, y), text[:150], font=FONT, fill=color)
            y += LINE_H
        if self.caption:
            d.rectangle([0, H - 130, W, H], fill=CAPTION_BG)
            d.text((MARGIN_X, H - 105), self.caption, font=FONT_CAPTION, fill=FG)
        return img

    def hold(self, seconds: float):
        img = self._render()
        path = self.frames_dir / f"f{self.n:05d}.png"
        img.save(path)
        self.stills.append((path, seconds))
        self.n += 1

    def type_command(self, cmd: str, cps: int = 40):
        """Animate typing at the prompt, ~cps chars/sec, chunked."""
        chunk = 3
        for i in range(0, len(cmd) + 1, chunk):
            shown = PROMPT + cmd[:i] + "▌"
            if self.rows and self.rows[-1][0].startswith(PROMPT):
                self.rows[-1] = (shown, FG)
            else:
                self.rows.append((shown, FG))
            self.hold(chunk / cps)
        self.rows[-1] = (PROMPT + cmd, FG)
        self.hold(0.35)

    def show_output(self, text: str, hold_after: float = 2.2):
        for line in text.splitlines():
            self.rows.append((line, line_color(line)))
        self.hold(hold_after)

    def blank_line(self):
        self.rows.append(("", FG))

    def title_card(self, title: str, subtitle: str, seconds: float = 3.0):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((W // 2, H // 2 - 60), title, font=FONT_TITLE, fill=FG, anchor="mm")
        d.text((W // 2, H // 2 + 30), subtitle, font=FONT_CAPTION, fill=DIM, anchor="mm")
        path = self.frames_dir / f"f{self.n:05d}.png"
        img.save(path)
        self.stills.append((path, seconds))
        self.n += 1

    def encode(self, out_path: Path):
        import imageio_ffmpeg

        concat = OUT / "concat.txt"
        with concat.open("w", encoding="utf-8") as fh:
            for path, dur in self.stills:
                fh.write(f"file 'frames/{path.name}'\n")
                fh.write(f"duration {dur:.3f}\n")
            fh.write(f"file 'frames/{self.stills[-1][0].name}'\n")  # concat quirk
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
             "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264",
             "-preset", "medium", "-crf", "20", str(out_path)],
            cwd=self.frames_dir.parent, check=True, capture_output=True,
        )


def run(cmd: str, cwd: Path = S4) -> str:
    """Execute for real via Git Bash (sed + venv CLIs on PATH); return
    combined output verbatim."""
    proc = subprocess.run(
        [BASH, "-c", cmd], cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", env=ENV,
    )
    return (proc.stdout + proc.stderr).rstrip("\n")


def main() -> int:
    OUT.mkdir(exist_ok=True)

    print("staging fresh scene4 assets…")
    stage = subprocess.run([BASH, "stage_scene4.sh"], cwd=HERE,
                           capture_output=True, text=True, encoding="utf-8", env=ENV)
    if stage.returncode != 0:
        print(stage.stdout, stage.stderr)
        return 1

    r = Recorder()

    r.title_card("Try to cheat it",
                 "Every command and every output line in this scene is real."
                 " · FIELD Platform, Spin State Labs")

    # Beat A — genuine chain + signed anchor
    r.caption = ("Auditors should assume tampering. First: the genuine ledger, "
                 "verified against its signed anchor.")
    cmd_a = ("ledger verify --path events.jsonl --anchors anchors.jsonl "
             "--pubkey keys/anchor-public.pem")
    r.type_command(cmd_a)
    r.show_output(run(cmd_a), hold_after=2.8)
    r.blank_line()

    # Beat B — one-keystroke tamper
    r.caption = ("Change one number — 1200 becomes 12 — and verification "
                 "names the exact record.")
    cmd_edit = "sed -i 's/\"amount\":1200/\"amount\":12/' tamper-me.jsonl"
    r.type_command(cmd_edit)
    r.show_output(run(cmd_edit), hold_after=0.5)
    # prove the edit on screen with a real read-back, never a claim
    cmd_show = "grep -o '\"invoice\":\"INV-001\",\"amount\":[0-9]*' tamper-me.jsonl"
    r.type_command(cmd_show)
    r.show_output(run(cmd_show), hold_after=1.6)
    cmd_b = "ledger verify --path tamper-me.jsonl"
    r.type_command(cmd_b)
    r.show_output(run(cmd_b), hold_after=3.0)
    r.blank_line()

    # Beat C — the smart attacker
    r.caption = ("A smarter attacker rewrites the ENTIRE history — every hash "
                 "recomputed, the refusal and the kill erased.")
    cmd_c1 = "ledger verify --path forged-events.jsonl"
    r.type_command(cmd_c1)
    r.show_output(run(cmd_c1), hold_after=2.2)
    r.caption = "The naive check is fooled. The anchor is not."
    cmd_c2 = ("ledger verify --path forged-events.jsonl --anchors anchors.jsonl "
              "--pubkey keys/anchor-public.pem")
    r.type_command(cmd_c2)
    r.show_output(run(cmd_c2), hold_after=4.0)

    r.caption = ("A signed fingerprint stored off the box catches what the "
                 "chain alone cannot. We tell you which attacks each layer stops.")
    r.hold(3.0)

    r.title_card("Declared vs. Enforced",
                 "Force Field Protocol · FIELD Platform · Spin State Labs — "
                 "Humans organize; AI operates.")

    out_path = OUT / "scene4.mp4"
    print(f"encoding {len(r.stills)} stills…")
    r.encode(out_path)
    total = sum(d for _, d in r.stills)
    print(f"written: {out_path} (~{total:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
