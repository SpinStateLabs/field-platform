"""Orchestration: inputs → findings → (report, signed pack).

``run_retro`` is pure apart from READING the input files. ``write_outputs``
is the only function that writes, and it refuses to write over an input.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .clauses import evaluate, sessionize
from .evidence import build_pack
from .models import TOOL_NAME, TOOL_VERSION, RetroConfig, RetroResult
from .parsers import read_input, resolve_parser, unique_labels
from .report import render_markdown


def run_retro(
    paths: list[Path],
    fmt: str = "clf",
    preset: str = "generic",
    overrides: dict[str, str] | None = None,
    config: RetroConfig | None = None,
) -> RetroResult:
    if not paths:
        raise ValueError("at least one log file is required")
    config = config or RetroConfig()
    parser = resolve_parser(fmt, preset, overrides)
    inputs = []
    requests = []
    for path, label in zip(paths, unique_labels(paths)):
        info, reqs = read_input(path, label, fmt, parser)
        inputs.append(info)
        requests.extend(reqs)
    sessions = sessionize(requests, config)
    findings, campaigns, verdicts = evaluate(sessions, config)
    grades = Counter(f.grade.value for f in findings)
    counts: dict[str, Any] = {
        "verdicts": verdicts,
        "grades": dict(sorted(grades.items())),
        "campaigns": len(campaigns),
        "findings": len(findings),
    }
    ts = sorted(r.ts for r in requests)
    return RetroResult(
        tool={"name": TOOL_NAME, "version": TOOL_VERSION},
        config=config,
        inputs=inputs,
        sessions_total=len(sessions),
        requests_total=len(requests),
        window_first=ts[0] if ts else None,
        window_last=ts[-1] if ts else None,
        findings=findings,
        campaigns=campaigns,
        counts=counts,
    )


def write_outputs(
    result: RetroResult,
    out_dir: Path,
    private_key_pem: str,
    generated_at: str,
    inputs: list[Path],
    force: bool = False,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"
    pack_path = out_dir / "evidence-pack.json"
    existing_inputs = [p for p in inputs if p.exists()]

    def _is_input(target: Path) -> bool:
        # resolve() catches symlinks and ./.. ; samefile catches HARD links
        # (same inode, different path) that resolve() alone would miss.
        rt = target.resolve()
        if any(rt == p.resolve() for p in inputs):
            return True
        if target.exists():
            for p in existing_inputs:
                try:
                    if target.samefile(p):
                        return True
                except OSError:
                    pass
        return False

    for target in (report_path, pack_path):
        if _is_input(target):
            raise ValueError(f"refusing to write over an input file: {target}")
        if target.exists() and not force:
            raise FileExistsError(f"{target} exists (use --force to overwrite)")
    report = render_markdown(result, generated_at)
    pack = build_pack(result, report, generated_at, private_key_pem)
    import json

    report_path.write_text(report, encoding="utf-8", newline="\n")
    # ensure_ascii=True: the signed evidence pack is a cross-platform interchange
    # artifact, so it must be pure ASCII on disk (a non-ASCII char like "→" read
    # back under a cp1252 locale would corrupt and fail verification). The pack
    # SIGNATURE is over field_core canonical bytes of the dict, so escaping a
    # char in the file does not change it — json.loads reconstructs the same str.
    pack_path.write_text(json.dumps(pack, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    return report_path, pack_path
