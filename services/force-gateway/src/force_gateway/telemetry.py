"""Hygiene telemetry — DETERMINISTIC REGEX HEURISTICS, clearly labeled.

These counters detect surface markers of FORCE compliance in response text.
They are string patterns, not judgments: a response can satisfy the letter
of every marker and still be wrong, and vice versa. The dashboard labels
every figure "heuristic" for exactly that reason.
"""

from __future__ import annotations

import re
from pydantic import BaseModel

METHOD_LABEL = (
    "regex heuristic v0.1 — surface markers only, no semantic judgment, no LLM"
)

# [E] Express uncertainty: HIGH/MEDIUM/LOW tags in bold, brackets, or
# followed by a separator (matches the protocol's tagging convention).
_CONFIDENCE = re.compile(r"\*\*(HIGH|MEDIUM|LOW)\*\*|\[(HIGH|MEDIUM|LOW)\]")

# [F] Corrections issued (the protocol demands direct correction).
_CORRECTION = re.compile(
    r"(?i)\b(correction:|that (is|'s) incorrect|the premise is (wrong|flawed|false)|"
    r"i need to correct|this is not (correct|accurate))"
)

# [F] Flattery / filler the protocol forbids.
_FLATTERY = re.compile(
    r"(?i)\b(great question|excellent question|i'd be happy to|happy to help|"
    r"hope this helps|certainly!|let me know if)"
)

# [C] Chain-of-thought structure markers.
_ASSUMPTIONS = re.compile(r"^ASSUMPTIONS:", re.M)
_REASONING = re.compile(r"^REASONING:", re.M)
_CONCLUSION = re.compile(r"^CONCLUSION:", re.M)

# [O] Objections-first markers.
_OBJECTION = re.compile(r"(?i)\b(objection|failure (condition|mode|scenario)|would break)")

# [R] Source honesty markers.
_SOURCE_HONESTY = re.compile(r"(?i)(not in source|i don't know|general knowledge|training data)")


class HygieneReport(BaseModel):
    confidence_tags: int
    has_confidence_tags: bool
    corrections: int
    flattery_hits: int
    clean_of_flattery: bool
    cot_structure: bool  # ASSUMPTIONS + REASONING + CONCLUSION all present
    objection_markers: int
    source_honesty_markers: int
    method: str = METHOD_LABEL


def analyze(text: str) -> HygieneReport:
    confidence = len(_CONFIDENCE.findall(text))
    flattery = len(_FLATTERY.findall(text))
    return HygieneReport(
        confidence_tags=confidence,
        has_confidence_tags=confidence > 0,
        corrections=len(_CORRECTION.findall(text)),
        flattery_hits=flattery,
        clean_of_flattery=flattery == 0,
        cot_structure=bool(
            _ASSUMPTIONS.search(text)
            and _REASONING.search(text)
            and _CONCLUSION.search(text)
        ),
        objection_markers=len(_OBJECTION.findall(text)),
        source_honesty_markers=len(_SOURCE_HONESTY.findall(text)),
    )
