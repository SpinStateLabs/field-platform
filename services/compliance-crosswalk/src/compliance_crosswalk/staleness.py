"""Regulatory-corpus staleness tracking — the crosswalk admits when it is old.

GOVERNANCE RATIONALE (ADR 07 §3/§4): every citation in ``mapping.py`` was
verified on one retrieval date. Regulations move; the mapping table does
not move with them by itself. Rather than silently presenting an aging
crosswalk as current, staleness is a first-class, persisted output: a
framework is flagged the moment a new version or amendment is spotted,
the flag stays visible until a NAMED human reviews it, and the report
states how long each flag has been open — the stale window is itself
evidence, not something to hide. Clearing a flag records who reviewed it;
it never touches the citations. Only a fresh ingestion (a new RETRIEVED
date in mapping.py, with the sources actually re-read) does that.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, RETRIEVED

# Derived, never typed twice: the corpus version cannot drift from the
# retrieval date the citations actually carry.
CORPUS_VERSION = f"corpus-{RETRIEVED}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StaleStore:
    """Persisted stale flags per framework, with a named-review history.

    On-disk shape (JSON, UTF-8)::

        {"corpus_version": ..., "active": {framework: flag}, "history": [...]}
    """

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            path = (
                Path(os.environ.get("FIELD_DATA_DIR", "."))
                / "crosswalk_stale_flags.json"
            )
        self.path = Path(path)
        self._active: dict[str, dict] = {}
        self._history: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():  # missing file = empty state, not an error
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._active = dict(data.get("active", {}))
        self._history = list(data.get("history", []))

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "corpus_version": CORPUS_VERSION,
            "active": self._active,
            "history": self._history,
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def mark(
        self, framework: str, reason: str, new_version: str | None = None
    ) -> dict:
        """Flag a framework as stale; idempotent on the detection clock.

        Re-marking updates the reason/new_version but keeps the original
        ``flagged_at`` — the stale window measures from FIRST detection,
        and restarting it would understate how long the flag stood.
        """
        if framework not in FRAMEWORKS:
            raise ValueError(
                f"unknown framework {framework!r}; known: {sorted(FRAMEWORKS)}"
            )
        existing = self._active.get(framework)
        flag = {
            "framework": framework,
            "flagged_at": existing["flagged_at"]
            if existing
            else _utc_now().isoformat(),
            "reason": reason,
            "new_version": new_version,
        }
        self._active[framework] = flag
        self._persist()
        return flag

    def clear(self, framework: str, reviewed_by: str) -> dict:
        """Clear a flag after review. The review is NAMED — no anonymous
        clears — and the cleared flag is preserved in history, so the
        record of having been stale outlives the flag itself."""
        if not reviewed_by or not reviewed_by.strip():
            raise ValueError(
                "reviewed_by must be a non-empty name — re-review is NAMED"
            )
        if framework not in self._active:
            raise KeyError(framework)
        flag = self._active.pop(framework)
        review = {
            "framework": framework,
            "reviewed_by": reviewed_by,
            "cleared_at": _utc_now().isoformat(),
            "flag": flag,
        }
        self._history.append(review)
        self._persist()
        return review

    def active(self) -> list[dict]:
        return sorted(self._active.values(), key=lambda f: f["framework"])

    def status(self) -> dict:
        """Current staleness posture. Each active flag carries its
        ``stale_window_seconds`` — per ADR 07, the length of the window
        is itself reported, never summarized away."""
        now = _utc_now()
        active = []
        for flag in self.active():
            entry = dict(flag)
            flagged_at = datetime.fromisoformat(flag["flagged_at"])
            entry["stale_window_seconds"] = (now - flagged_at).total_seconds()
            active.append(entry)
        return {
            "corpus_version": CORPUS_VERSION,
            "active": active,
            "history": list(self._history),
        }


def affected_controls(framework: str) -> list[str]:
    """Control ids whose mapping actually cites the framework.

    Only ``cited`` entries are affected by a regulatory version change —
    pending entries reference no text, so there is nothing to go stale.
    """
    if framework not in FRAMEWORKS:
        raise ValueError(
            f"unknown framework {framework!r}; known: {sorted(FRAMEWORKS)}"
        )
    return sorted(
        control.control_id
        for control in CONTROLS
        if control.citations[framework].status == "cited"
    )
