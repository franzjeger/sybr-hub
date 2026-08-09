"""Matching company names across systems that do not share an id.

IT Glue, UniFi Site Manager and Partner Center each know a customer by a name a
human typed, and nothing joins them. Scoring follows the Uniweb matcher already
in the tree — exact 1.0, whole-word containment 0.85, SequenceMatcher otherwise
— so this codebase has one notion of "matched" rather than three that disagree.
"""

from __future__ import annotations

import re as _re
from difflib import SequenceMatcher
from typing import Any

# Legal-form suffixes carry no identity: "Acme AS" and "Acme" are one company,
# and leaving them in drags an otherwise exact match below the threshold.
_ORG_SUFFIXES = {
    "as", "asa", "ab", "a/s", "ans", "da", "ba", "sa", "nuf", "enk",
    "ltd", "limited", "inc", "llc", "gmbh", "oy", "aps",
}
MATCH_AUTO = 0.75
# Two candidates this close cannot be told apart by name alone. Picking the
# higher one would be a coin flip written into a customer record.
MATCH_AMBIGUOUS_GAP = 0.05


def normalise_org_name(name: Any) -> str:
    """Lowercase, strip punctuation and drop the legal-form suffix."""
    if not isinstance(name, str):
        return ""
    # Dots and slashes are dropped rather than spaced, so "A/S" and "Ltd."
    # survive as single suffix words instead of splintering into letters that
    # no suffix list can match. Everything else, hyphens included, becomes a
    # space: "A-Tre" and "A Tre" are the same company written two ways.
    cleaned = _re.sub(r"[./]", "", name.lower())
    cleaned = _re.sub(r"[^\w\s]", " ", cleaned).replace("_", " ")
    words = [w for w in cleaned.split() if w]
    while words and words[-1] in _ORG_SUFFIXES:
        words.pop()
    return " ".join(words)


def _is_word_run(haystack: list[str], needle: list[str]) -> bool:
    """True when *needle* appears in *haystack* as whole consecutive words."""
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[i:i + len(needle)] == needle
        for i in range(len(haystack) - len(needle) + 1)
    )


def score_name_match(left: str, right: str) -> float:
    """Similarity between two normalised names, on the Uniweb scale.

    Containment is tested on whole words, not raw substring. "star bil" is a
    substring of "star bilskade avd skien" only because *bil* begins
    *bilskade* — and Star Bil AS and Star Bilskade AS are different companies.
    A rule that fires inside a word scored that pairing 0.85, which reads as
    confident, and the resulting link would have been silently wrong.
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_words, right_words = left.split(), right.split()
    if _is_word_run(right_words, left_words) or _is_word_run(left_words, right_words):
        return 0.85
    return SequenceMatcher(None, left, right).ratio()


def match_by_name(
    incoming: str,
    candidates: list[tuple[str, Any]],
) -> tuple[Any, float, str]:
    """Best candidate for *incoming*, with a confidence that admits doubt.

    ``candidates`` are ``(name, payload)`` pairs. Returns
    ``(payload, score, confidence)`` where confidence is high, ambiguous, low
    or none — ambiguous when the runner-up is within a hair of the winner,
    because choosing between those on score is a coin flip.
    """
    normalised = normalise_org_name(incoming)
    if not normalised or not candidates:
        return (None, 0.0, "none")

    scored = sorted(
        ((score_name_match(normalised, normalise_org_name(name)), payload)
         for name, payload in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0

    if best_score >= MATCH_AUTO and (best_score - runner_up) < MATCH_AMBIGUOUS_GAP:
        return (best, best_score, "ambiguous")
    if best_score >= MATCH_AUTO:
        return (best, best_score, "high")
    if best_score >= 0.5:
        return (best, best_score, "low")
    return (None, best_score, "none")
