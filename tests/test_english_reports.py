"""An English report reads English, outside what the tenant itself wrote.

The report engine was written in Norwegian first and translated in places:
the CIS details, the "cannot be verified" prefix, the score's data gaps, the
house standard's requirements, the network section's labels and the frozen
words in stored recommendations all reached an English report in Norwegian.
Each was fixed at its source with a key; these tests keep it that way.

What a reader sees is checked, not the source: both templates are rendered
in English from the audit fixtures and every text node is scanned for
Norwegian. Text the tenant wrote is data and stays as written: a node that is
a piece of one of the run's own files (a group name, a raw evidence file) is
left out, and so is a value from the parsed context. Nothing else is.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

from app.reports.compliance import _build_compliance_map
from app.reports.generator import _jinja_env, build_report_context
from app.reports.i18n import T
from app.reports.recommendations import _build_recommendations
from tests import compliance_characterisation as cc
from tests import recommendations_characterisation as rc
from tests.audit_fixture import BROKEN_AUDIT, FULL_AUDIT

TEMPLATES = ("report_customer.html.j2", "report_tech.html.j2")

# Characters and words that are Norwegian and not English. A word shared by
# both languages ("for", "no", "under") would only make the scan noisy.
_NORWEGIAN = re.compile(
    r"[æøåÆØÅ]|\b(?:og|ikke|ble|blir|kunde\w*|bruker\w*|ingen|funnet|aktivert|deaktivert|"
    r"utilgjengelig|konfigurert|eller|mangler|kunne|leses|oppdaget|verifiseres|lisensiert|"
    r"tildelt|uten|krever|innstillinger|dager|ukjent|samlet|hentet|feilet|kjør|dette|denne|"
    r"hvis|har|skal|enheter|enhet|nettverk|brannmur\w*|modell|klienter|gjest\w*|ja|nei|"
    r"aktive|tilgjengelig\w*|passord|utdatert|anbefal\w*|tiltak|sikkerhet\w*|samsvar\w*|"
    r"policyer|tilgang\w*|varsl\w*|oppbevaring\w*|sammendrag|hovedfunn|middels|lav|kritisk|"
    r"med|vises|postboks\w*|postkasse\w*|videresend\w*|nøkkel\w*|risiko\w*|lenke\w*)\b",
    re.IGNORECASE,
)

# Data values that contain Norwegian and reach the page in a shape that is not
# a piece of any one file. Each needs its reason; none does today.
_DATA_ALLOWLIST: dict[str, str] = {}


def _norwegian(text: str) -> bool:
    for value in _DATA_ALLOWLIST:
        text = text.replace(value, " ")
    return bool(_NORWEGIAN.search(text))


def _text_nodes(page: str) -> list[str]:
    """What a reader sees, one node at a time: text between tags and titles."""
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    page = re.sub(r"<!--.*?-->", " ", page, flags=re.S)
    nodes = re.split(r"<[^>]*>", page)
    nodes += re.findall(r'\b(?:title|alt|aria-label|placeholder)="([^"]*)"', page)
    return [" ".join(html.unescape(n).split()) for n in nodes if n.strip()]


def _is_data(node: str, files: dict[str, str]) -> bool:
    """A node that is a piece of one of the run's files, word for word."""
    pattern = re.compile(r"(?<!\w)" + re.escape(node).replace(r"\ ", r"\s+") + r"(?!\w)")
    return any(pattern.search(text) for text in files.values())


def _render(tmp_path: Path, files: dict[str, str]) -> dict[str, str]:
    run = tmp_path / "Acme_AS" / "2026-01-01_0900"
    run.mkdir(parents=True)
    for name, content in files.items():
        (run / name).write_text(content, encoding="utf-8")
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang="en", persist_metrics=False)
    ctx["t"], ctx["lang"], ctx["theme"] = T("en"), "en", "light"
    env = _jinja_env()
    return {name: env.get_template(name).render(**ctx) for name in TEMPLATES}


def _every_file_refused() -> dict[str, str]:
    return {name: "Error: 403 Forbidden\n" for name in FULL_AUDIT}


def _direct_unifi_and_unreadable_fortigate() -> dict[str, str]:
    unifi = {
        "mode": "direct",
        "device_count": 2,
        "reachable": 1,
        "default_creds_count": 1,
        "outdated_firmware_count": 1,
        "eol_count": 1,
        "devices": [
            {"host": "192.0.2.10", "model": "U6-Pro", "mac": "00:00:5e:00:53:01", "ok": True},
            {"host": "192.0.2.11", "ok": False, "error": "timeout"},
        ],
    }
    return {
        **BROKEN_AUDIT,
        "60_fortigate_audit.txt": "{not json",
        "61_unifi_audit.txt": json.dumps(unifi),
    }


FIXTURES = {
    "healthy tenant": FULL_AUDIT,
    "tenant with every finding": BROKEN_AUDIT,
    "direct UniFi, unreadable FortiGate": _direct_unifi_and_unreadable_fortigate(),
    "every section refused": _every_file_refused(),
    "nothing collected": {},
}


@pytest.mark.parametrize("fixture", FIXTURES, ids=list(FIXTURES))
def test_an_english_report_has_no_norwegian_outside_the_tenants_data(tmp_path, fixture):
    files = FIXTURES[fixture]
    for template, page in _render(tmp_path, files).items():
        norwegian = sorted(
            {n for n in _text_nodes(page) if _norwegian(n) and not _is_data(n, files)}
        )
        assert not norwegian, f"{template} ({fixture}) shows Norwegian:\n" + "\n".join(norwegian)


def test_the_scan_finds_norwegian_when_there_is_some(tmp_path):
    """The scan above would pass on anything if it could not see Norwegian."""
    page = _render(tmp_path, FULL_AUDIT)["report_customer.html.j2"]
    nodes = _text_nodes(page.replace("</body>", "<p>Kan ikke verifiseres: data</p></body>"))
    assert [n for n in nodes if _norwegian(n) and not _is_data(n, FULL_AUDIT)] == [
        "Kan ikke verifiseres: data"
    ]


# ── Every branch, not only the ones a fixture reaches ─────────────────────────


def _context_strings(value) -> set[str]:
    """Every string in a parsed context but the collectors' files: data, as written."""
    if isinstance(value, str):
        return {value} if len(value) >= 3 else set()
    if isinstance(value, dict):
        return {s for k, v in value.items() if k != "file_contents" for s in _context_strings(v)}
    if isinstance(value, list | tuple):
        return {s for v in value for s in _context_strings(v)}
    return set()


def _without(text: str, data: set[str]) -> str:
    for value in sorted(data, key=len, reverse=True):
        text = text.replace(value, " ")
    return text


def test_every_compliance_detail_is_english_in_an_english_report():
    """All 821 stored contexts, which between them reach every verdict branch.

    A context value shown as it is (a SharePoint sharing label the parser
    wrote in the run's language, a collector's refusal) is data here.
    """
    norwegian = {}
    for name, context, _ in cc.stored_contexts(cc.load()):
        try:
            rows = _build_compliance_map(cc.clone(context), lang="en", frameworks="cis")
        except Exception:
            continue  # the snapshot pins which inputs raise, and with what
        data = _context_strings(context)
        for row in rows:
            detail = _without(str(row["detail"]), data)
            if _norwegian(detail):
                norwegian.setdefault(str(row["detail"]), name)
    assert not norwegian, "\n".join(f"{d!r}  ({n})" for d, n in sorted(norwegian.items()))


def test_every_recommendation_is_english_in_an_english_report():
    norwegian = {}
    for name, context, _ in rc.stored_contexts(rc.load()):
        try:
            recs = _build_recommendations(**rc.clone(context), lang="en")
        except Exception:
            continue
        data = _context_strings(context)
        for rec in recs:
            texts = [rec.get("title"), rec.get("detail"), rec.get("effort")]
            for text in [*texts, *(rec.get("sub_items") or [])]:
                if _norwegian(_without(str(text or ""), data)):
                    norwegian.setdefault(str(text), name)
    assert not norwegian, "\n".join(f"{t!r}  ({n})" for t, n in sorted(norwegian.items()))


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (BROKEN_AUDIT, "4 PIM-berettigede rolletildelinger funnet"),
        (_every_file_refused(), "Kan ikke verifiseres: PIM-data utilgjengelig"),
    ],
    ids=["reading", "no reading"],
)
def test_the_norwegian_report_still_reads_norwegian(tmp_path, files, expected):
    """The keys have a Norwegian side, and the Norwegian report uses it."""
    run = tmp_path / "Acme_AS" / "2026-01-01_0900"
    run.mkdir(parents=True)
    for name, content in files.items():
        (run / name).write_text(content, encoding="utf-8")
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang="no", persist_metrics=False)
    details = {c["cis_id"]: str(c["detail"]) for c in ctx["compliance"]}
    assert details["1.1.5"] == expected
    assert ctx["baseline"]["checks"][0]["title"].startswith("Minst")


def test_the_house_standard_is_judged_in_the_reports_language(tmp_path):
    run = tmp_path / "Acme_AS" / "2026-01-01_0900"
    run.mkdir(parents=True)
    for name, content in FULL_AUDIT.items():
        (run / name).write_text(content, encoding="utf-8")
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang="en", persist_metrics=False)
    titles = [c["title"] for c in ctx["baseline"]["checks"]]
    assert "At least three enabled Conditional Access policies" in titles
