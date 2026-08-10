"""Shared terminal-replay renderer for the capstone video scenes.

Same honesty contract as record_scene4.py: commands are executed, output is
verbatim capture; typing animation and captions are presentation only.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
OUT = HERE / "out"
W, H = 1920, 1080
FPS = 30
MARGIN_X, MARGIN_TOP = 70, 60
LINE_H = 34
MAX_ROWS = 24

BG = (13, 17, 22)
FG = (219, 228, 236)
DIM = (125, 139, 153)
GREEN = (63, 185, 107)
RED = (224, 92, 79)
AMBER = (224, 166, 60)
ACCENT = (77, 159, 220)
CAPTION_BG = (23, 30, 38)

FONT = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 24)
FONT_CAPTION = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 30)
FONT_TITLE = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 54)

BASH = r"D:\Apps\Git\usr\bin\bash.exe"  # NOT the WSL bash on PATH
_home_win = os.environ.get("USERPROFILE") or os.environ.get("HOME", "")
_home_posix = "/" + _home_win[0].lower() + _home_win[2:].replace("\\", "/")
ENV = {**os.environ, "HOME": _home_posix}
ENV["PATH"] = (str(Path(_home_win) / ".venvs" / "field-platform" / "Scripts")
               + os.pathsep + ENV.get("PATH", ""))


def line_color(text: str):
    t = text.strip()
    if t.startswith("TAMPERED") or "ANCHOR FAILURE" in t or "BLOCK" in t:
        return RED
    if t.startswith("OK — ") or "VALID" in t or "drafted" in t or "ALLOW" in t:
        return GREEN
    if "ESCALATE" in t:
        return AMBER
    if t.startswith(("──", "══", "===")):
        return ACCENT
    return FG


def run(cmd: str, cwd: Path) -> str:
    """Capture verbatim; tolerate stray legacy-codepage bytes from inner
    tools (rendered as '-') rather than dropping real output."""
    proc = subprocess.run([BASH, "-c", cmd], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          env=ENV)
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.replace("�", "-").rstrip("\n")


class Recorder:
    def __init__(self, name: str, header: str):
        self.header = header
        self.stills: list[tuple[Path, float]] = []
        self.frames_dir = OUT / f"frames-{name}"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.rows: list[tuple[str, tuple]] = []
        self.caption = ""

    # -- frame construction ------------------------------------------------
    def _caption_lines(self):
        if not self.caption:
            return []
        words, lines, cur = self.caption.split(), [], ""
        for word in words:
            if len(cur) + len(word) + 1 > 105:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        lines.append(cur)
        return lines[:2]

    def _render(self) -> Image.Image:
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 42], fill=CAPTION_BG)
        d.text((MARGIN_X, 8), self.header, font=FONT, fill=DIM)
        y = MARGIN_TOP
        for text, color in self.rows[-MAX_ROWS:]:
            d.text((MARGIN_X, y), text[:150], font=FONT, fill=color)
            y += LINE_H
        cap = self._caption_lines()
        if cap:
            d.rectangle([0, H - 140, W, H], fill=CAPTION_BG)
            cy = H - 118
            for line in cap:
                d.text((MARGIN_X, cy), line, font=FONT_CAPTION, fill=FG)
                cy += 40
        return img

    def _save(self, img: Image.Image, seconds: float):
        path = self.frames_dir / f"f{self.n:05d}.png"
        img.save(path)
        self.stills.append((path, seconds))
        self.n += 1

    # -- authoring ---------------------------------------------------------
    def hold(self, seconds: float):
        self._save(self._render(), seconds)

    def type_command(self, cmd: str, prompt: str = "field-platform $ ",
                     cps: int = 40):
        chunk = 3
        for i in range(0, len(cmd) + 1, chunk):
            shown = prompt + cmd[:i] + "▌"
            if self.rows and self.rows[-1][0].startswith(prompt):
                self.rows[-1] = (shown, FG)
            else:
                self.rows.append((shown, FG))
            self.hold(chunk / cps)
        self.rows[-1] = (prompt + cmd, FG)
        self.hold(0.35)

    def show_output(self, text: str, hold_after: float = 2.2):
        for line in text.splitlines():
            self.rows.append((line, line_color(line)))
        self.hold(hold_after)

    def stream_output(self, text: str, triggers: list[tuple[str, str, float]],
                      base_hold: float = 0.22):
        """Reveal output line by line. triggers: (substring, caption, hold)."""
        for line in text.splitlines():
            self.rows.append((line, line_color(line)))
            hold = base_hold
            for needle, caption, t_hold in triggers:
                if needle and needle in line:
                    if caption:
                        self.caption = caption
                    hold = t_hold
                    break
            self.hold(hold)

    def blank_line(self):
        self.rows.append(("", FG))

    def title_card(self, title: str, subtitle: str, seconds: float = 3.0):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((W // 2, H // 2 - 60), title, font=FONT_TITLE, fill=FG, anchor="mm")
        d.text((W // 2, H // 2 + 30), subtitle, font=FONT_CAPTION, fill=DIM,
               anchor="mm")
        self._save(img, seconds)

    def image_still(self, png: Path, seconds: float):
        """Letterbox an external screenshot onto the canvas (real pixels)."""
        shot = Image.open(png).convert("RGB")
        scale = min(W / shot.width, (H - 150) / shot.height)
        shot = shot.resize((int(shot.width * scale), int(shot.height * scale)))
        img = Image.new("RGB", (W, H), BG)
        img.paste(shot, ((W - shot.width) // 2, 50))
        d = ImageDraw.Draw(img)
        cap = self._caption_lines()
        if cap:
            d.rectangle([0, H - 140, W, H], fill=CAPTION_BG)
            cy = H - 118
            for line in cap:
                d.text((MARGIN_X, cy), line, font=FONT_CAPTION, fill=FG)
                cy += 40
        self._save(img, seconds)

    # -- encoding ----------------------------------------------------------
    def encode(self, out_path: Path):
        import imageio_ffmpeg

        concat = OUT / f"concat-{self.frames_dir.name}.txt"
        with concat.open("w", encoding="utf-8") as fh:
            for path, dur in self.stills:
                fh.write(f"file '{self.frames_dir.name}/{path.name}'\n")
                fh.write(f"duration {dur:.3f}\n")
            fh.write(f"file '{self.frames_dir.name}/{self.stills[-1][0].name}'\n")
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat.name,
             "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264",
             "-preset", "medium", "-crf", "20", str(out_path)],
            cwd=OUT, check=True, capture_output=True,
        )
        return sum(d for _, d in self.stills)
