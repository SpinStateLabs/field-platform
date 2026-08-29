"""Deterministic routing predicate — which actions need semantic judgment.

S2 ships this as a MEASUREMENT-ONLY classifier: engine behavior is unchanged
(paraphrased actions still hard-block on exact scope membership). S3 attaches
the semantic judge to this same predicate, so the scorecard's
routing-predicate coverage is measured against the exact gate the judge will
sit behind.

Fires when an action is NOT an exact member of the declared scope but shares
at least one content word with a scope entry — the paraphrase neighborhood
the deterministic engine cannot resolve. Plain scope breaches (no shared
vocabulary) stay structural: deterministically blockable, no judge needed.
"""

from __future__ import annotations

import re
from typing import Iterable

_STOPWORDS = frozenset(
    {"a", "an", "and", "for", "from", "of", "or", "the", "to", "with"}
)

_WORD = re.compile(r"[a-z0-9]+")


def _content_tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS)


def needs_semantic_judgment(action: str, scopes: Iterable[str]) -> bool:
    """True when ``action`` is outside exact scope membership but shares
    vocabulary with a scope entry — the cases ADR 02 routes to the judge."""
    scope_list = list(scopes)
    if action in scope_list:
        return False
    tokens = _content_tokens(action)
    if not tokens:
        return False
    return any(tokens & _content_tokens(entry) for entry in scope_list)
