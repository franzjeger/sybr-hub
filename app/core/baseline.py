"""Baselines: a named, versioned standard a customer is measured against.

CIS and NIST say what good looks like in general. A baseline says what *this
MSP* requires of a customer, with a version on it, so a report stops being a
generic score and becomes a thing a customer can be brought up to. That is
the piece Inforcer has and we did not — theirs is a set of policies to
deploy, ours is a standard to measure against, and the second is what suits a
read-mostly tool.

**A check that could not be assessed does not fail.** Every check declares
``measured_when``: an expression that must hold before its evidence counts
for anything. When it does not hold the check reports not_measured, and
conformance is quoted over the checks that *were* assessed, with the rest
counted beside it rather than folded in.

That rule is the whole reason this is worth having. A baseline that scores an
unreadable section as non-conformant hands a customer a remediation task for
something nobody looked at; one that scores it as conformant is worse. This
codebase has found that mistake in the Intune section, the MFA figure, CIS
6.1.1, password protection and Purview, all in one week — so the standard
that judges them is not going to reintroduce it.

Baselines are data, not code. A new one is a JSON file, which is what lets a
technician argue about the threshold without touching the evaluator.

**Nothing here is prose a person reads.** A check returns a ``reason_code``
and the values behind it; the report template and the browser turn that into
a sentence in the reader's own language. The first version of this module
wrote English sentences into ``detail`` while the baseline document carried
Norwegian titles, so one card showed both languages at once and neither could
be translated. A core module that emits finished text has picked a language
on behalf of every caller.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any

logger = logging.getLogger(__name__)

BASELINE_DIR = pathlib.Path(__file__).parent.parent / "baselines"

# Every reason a check can give, as a code. The presentation layers translate
# these; tests/test_i18n_coverage.py asserts both tables carry all of them in
# both languages, and that this tuple has not drifted from the source.
REASON_CODES = ("met", "unmet", "guard_unset", "field_absent", "incomparable")

PASS = "pass"
FAIL = "fail"
NOT_MEASURED = "not_measured"

DEFAULT_BASELINE_ID = "sybr-standard"


def default_baseline_id() -> str:
    """The standard every report is measured against unless told otherwise.

    An environment variable rather than a stored setting: a report is built by
    the scheduler as well as by a request, and the two must not be able to
    disagree about which standard judged a run. The version travelling in the
    result is what keeps last year's verdict readable after the bar moves.
    """
    return (os.environ.get("SYBR_BASELINE") or "").strip() or DEFAULT_BASELINE_ID


class BaselineError(Exception):
    """A baseline document is malformed."""


def _resolve(context: dict, path: str) -> Any:
    """Walk a dotted path through the report context.

    Returns _MISSING rather than None for an absent path: a check on
    ``mfa.registered_pct`` must be able to tell a tenant at 0% from a context
    that never carried the field, and None is what several of those fields
    legitimately hold when a figure was not measured.
    """
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"

    def __bool__(self) -> bool:
        return False


_MISSING = _Missing()


LANGUAGES = ("no", "en")


def localised(value: Any, lang: str) -> str:
    """Pick one language out of a baseline's {"no": ..., "en": ...} field."""
    if isinstance(value, dict):
        return str(value.get(lang) or value.get("no") or "")
    return str(value or "")


def _truthy(value: Any) -> bool:
    return not isinstance(value, _Missing) and bool(value)


_OP_SYMBOL = {
    "gte": "\u2265", "gt": ">", "lte": "\u2264", "lt": "<",
    "eq": "=", "ne": "\u2260", "is_true": "=", "is_false": "=",
}

_OPERATORS = {
    "gte": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
    "lte": lambda a, b: a <= b,
    "lt": lambda a, b: a < b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


def evaluate_check(check: dict, context: dict, lang: str = "no") -> dict:
    """Judge one check against one audit's context.

    Returns a ``reason_code`` and the values behind it rather than a sentence.
    Formatting belongs to whoever knows the reader's language.
    """
    check_id = check.get("id", "?")
    result = {
        "id": check_id,
        "title": localised(check.get("title"), lang) or check_id,
        "why": localised(check.get("why"), lang),
        "severity": check.get("severity", "medium"),
        "status": NOT_MEASURED,
        "reason_code": "",
        "params": {},
    }

    guard = check.get("measured_when")
    if guard and not _truthy(_resolve(context, guard)):
        result["reason_code"] = "guard_unset"
        result["params"] = {"guard": guard}
        return result

    actual = _resolve(context, check["path"])
    if isinstance(actual, _MISSING.__class__) or actual is None:
        # Distinct from the guard above: the section reported itself readable
        # and then did not carry the field. That is a defect in the collector
        # or a renamed key, and calling it a failure would blame the customer
        # for it.
        result["reason_code"] = "field_absent"
        result["params"] = {"path": check["path"]}
        return result

    op = check.get("op", "eq")
    if op == "is_true":
        ok, expected = bool(actual) is True, True
    elif op == "is_false":
        ok, expected = bool(actual) is False, False
    elif op in _OPERATORS:
        expected = check["value"]
        try:
            ok = _OPERATORS[op](actual, expected)
        except TypeError:
            result["reason_code"] = "incomparable"
            result["params"] = {
                "path": check["path"], "actual": actual, "expected": expected,
            }
            return result
    else:
        raise BaselineError(f"Check {check_id!r} uses unknown operator {op!r}")

    result["status"] = PASS if ok else FAIL
    result["path"] = check["path"]
    result["actual"] = actual
    result["op"] = op
    result["expected"] = expected
    result["reason_code"] = "met" if ok else "unmet"
    result["params"] = {
        "path": check["path"], "actual": actual,
        "op": _OP_SYMBOL.get(op, op), "expected": expected,
    }
    return result


def load_baseline(baseline_id: str) -> dict:
    path = BASELINE_DIR / f"{baseline_id}.json"
    if not path.is_file():
        raise BaselineError(f"No baseline {baseline_id!r}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for field in ("id", "version", "name", "checks"):
        if field not in doc:
            raise BaselineError(f"Baseline {baseline_id!r} is missing {field!r}")
    seen: set[str] = set()
    for check in doc["checks"]:
        if "id" not in check or "path" not in check:
            raise BaselineError(f"A check in {baseline_id!r} lacks id or path")
        if check["id"] in seen:
            raise BaselineError(f"Duplicate check id {check['id']!r} in {baseline_id!r}")
        seen.add(check["id"])

    # Both languages, or the document does not load. A baseline that speaks
    # one language shows that language to every reader, and the cheapest
    # moment to catch that is before anybody sees the card. Checked after the
    # structural pass, so a duplicate id is not reported as a translation
    # problem.
    for check in doc["checks"]:
        for field in ("title", "why"):
            value = check.get(field)
            if not isinstance(value, dict) or not all(
                str(value.get(lang, "")).strip() for lang in LANGUAGES
            ):
                raise BaselineError(
                    f"Check {check['id']!r} in {baseline_id!r} must carry {field!r} "
                    f"in each of {', '.join(LANGUAGES)}"
                )
    return doc


def list_baselines(lang: str = "no") -> list[dict]:
    out = []
    for path in sorted(BASELINE_DIR.glob("*.json")):
        try:
            doc = load_baseline(path.stem)
        except BaselineError as exc:
            logger.warning("Skipping malformed baseline %s: %s", path.name, exc)
            continue
        out.append({
            "id": doc["id"], "version": doc["version"], "name": doc["name"],
            "description": localised(doc.get("description"), lang),
            "checks": len(doc["checks"]),
        })
    return out


def evaluate(baseline_id: str, context: dict, lang: str = "no") -> dict:
    """Judge one audit against one baseline.

    Conformance is quoted over the checks that could be assessed. The rest are
    counted beside it and never folded in: a baseline that reports 60% when a
    third of it could not be read is describing the audit, not the tenant.
    """
    doc = load_baseline(baseline_id)
    results = [evaluate_check(c, context, lang) for c in doc["checks"]]

    passed = [r for r in results if r["status"] == PASS]
    failed = [r for r in results if r["status"] == FAIL]
    unassessed = [r for r in results if r["status"] == NOT_MEASURED]
    assessed = len(passed) + len(failed)

    return {
        "baseline": {
            "id": doc["id"], "version": doc["version"], "name": doc["name"],
            "description": localised(doc.get("description"), lang),
        },
        "conformance_pct": round(len(passed) / assessed * 100, 1) if assessed else None,
        "passed": len(passed),
        "failed": len(failed),
        "assessed": assessed,
        "not_measured": len(unassessed),
        "total_checks": len(results),
        "checks": results,
    }
